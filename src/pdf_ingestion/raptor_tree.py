"""
RAPTOR tree builder — Phase 2.

Recursive Abstractive Processing for Tree-Organized Retrieval.

Algorithm
---------
1.  Fetch all chunk embeddings for a document from Qdrant.
2.  Cluster them with GaussianMixture (+ optional UMAP pre-reduction).
3.  For each cluster summarise the member chunks via Ollama/Llama 3.2.
4.  Embed each summary with Jina v3.
5.  Store summaries as RaptorNode rows in SQLite.
6.  Upsert summary vectors into Qdrant (source_type="raptor_summary").
7.  Repeat on level-1 summaries to build level 2 if doc is large enough.

Qdrant payload for RAPTOR points
---------------------------------
{
  "tenant_id":        "global",
  "source_type":      "raptor_summary",
  "is_global_baseline": true/false,
  "document_id":      "...",
  "raptor_node_id":   "...",
  "raptor_level":     1,
  "cluster_id":       0,
  "text":             "<summary text>",
  "child_chunk_count": 4,
  "embedding_version": "jina-v3"
}
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings


# ── Data contract ─────────────────────────────────────────────────────────

@dataclass
class RaptorNodeData:
    node_id:          str
    document_id:      str
    tenant_id:        str
    level:            int
    cluster_id:       int
    summary:          str
    child_ids:        list[str]   # chunk_ids (level 1) or node_ids (level 2)
    parent_id:        Optional[str] = None
    qdrant_point_id:  str = field(default_factory=lambda: str(uuid.uuid4()))
    embedding:        Optional[np.ndarray] = None


# ── Summarisation prompt ──────────────────────────────────────────────────

_SUM_PROMPT = """\
You are an expert physics educator writing a study summary.
Summarise the passages below into a single coherent paragraph (3-5 sentences) \
for an undergraduate student.

Rules:
- Use only information present in the passages. Do not add outside knowledge.
- Preserve the exact names of laws, theorems, quantities, and equations (e.g. "Newton's Second Law", "F = ma").
- State the key concept or principle first, then supporting ideas.
- If multiple distinct ideas are present, connect them with their logical relationship.
- Write in plain English — no bullet points, no headings.

PASSAGES:
{passages}

SUMMARY:"""


# ── RAPTOR builder ────────────────────────────────────────────────────────

class RaptorBuilder:
    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()

    # ── Public entry-point ────────────────────────────────────────────────

    def build_tree(
        self,
        document_id:        str,
        tenant_id:          str,
        is_global_baseline: bool,
        chunk_texts:        list[str],
        chunk_ids:          list[str],
        chunk_embeddings:   np.ndarray,
    ) -> list[RaptorNodeData]:
        """
        Build a 1-or-2 level RAPTOR tree and return all nodes.
        Caller is responsible for persisting them via the store.
        """
        n = len(chunk_texts)
        if n == 0:
            return []

        logger.info("Building RAPTOR tree for doc {} ({} chunks)", document_id, n)

        max_levels = self._cfg.raptor_max_levels

        # ── Level 1: cluster leaf chunks ──────────────────────────────────
        current_nodes = self._build_level(
            document_id=document_id,
            tenant_id=tenant_id,
            is_global_baseline=is_global_baseline,
            texts=chunk_texts,
            ids=chunk_ids,
            embeddings=chunk_embeddings,
            level=1,
            parent_id=None,
        )

        all_nodes: list[RaptorNodeData] = list(current_nodes)

        # ── Higher levels: keep building until max_levels or too few nodes ─
        for level in range(2, max_levels + 1):
            if len(current_nodes) < self._cfg.raptor_min_cluster_size:
                break

            prev_nodes = current_nodes
            # Filter in parallel so texts/ids/embeddings stay aligned
            valid_prev = [nd for nd in prev_nodes if nd.embedding is not None]
            if len(valid_prev) < 2:
                break
            level_embeddings = np.array(
                [nd.embedding for nd in valid_prev], dtype=np.float32
            )

            current_nodes = self._build_level(
                document_id=document_id,
                tenant_id=tenant_id,
                is_global_baseline=is_global_baseline,
                texts=[nd.summary  for nd in valid_prev],
                ids=[nd.node_id    for nd in valid_prev],
                embeddings=level_embeddings,
                level=level,
                parent_id=None,
            )

            # Wire parent_id using child_ids from the new nodes
            node_id_to_parent: dict[str, str] = {}
            for new_node in current_nodes:
                for child_id in new_node.child_ids:
                    node_id_to_parent[child_id] = new_node.node_id

            for prev_node in valid_prev:
                prev_node.parent_id = node_id_to_parent.get(prev_node.node_id)

            all_nodes.extend(current_nodes)

        logger.success(
            "RAPTOR tree built: {} nodes (levels {})",
            len(all_nodes),
            sorted({nd.level for nd in all_nodes}),
        )
        return all_nodes

    # ── Internals ─────────────────────────────────────────────────────────

    def _build_level(
        self,
        document_id: str,
        tenant_id: str,
        is_global_baseline: bool,
        texts: list[str],
        ids: list[str],
        embeddings: np.ndarray,
        level: int,
        parent_id: Optional[str],
    ) -> list[RaptorNodeData]:
        n = len(texts)

        # Determine number of clusters
        n_clusters = max(1, min(
            int(np.ceil(np.sqrt(n))),
            n // max(self._cfg.raptor_min_cluster_size, 1),
        ))

        if n_clusters <= 1 or n < 2:
            # Collapse everything into one summary node
            labels = [0] * n
        else:
            labels = self._cluster(embeddings, n_clusters)

        cluster_ids = sorted(set(labels))
        nodes: list[RaptorNodeData] = []

        for cid in cluster_ids:
            member_idxs  = [i for i, l in enumerate(labels) if l == cid]
            member_texts = [texts[i]  for i in member_idxs]
            member_ids   = [ids[i]    for i in member_idxs]

            summary = self._summarise(member_texts)
            embedding = self._embed(summary)

            nodes.append(
                RaptorNodeData(
                    node_id=str(uuid.uuid4()),
                    document_id=document_id,
                    tenant_id=tenant_id,
                    level=level,
                    cluster_id=cid,
                    summary=summary,
                    child_ids=member_ids,
                    parent_id=parent_id,
                    embedding=embedding,
                )
            )

        return nodes

    def _cluster(self, embeddings: np.ndarray, n_clusters: int) -> list[int]:
        """GMM clustering with optional UMAP pre-reduction."""
        from sklearn.mixture import GaussianMixture

        X = embeddings

        # UMAP dimensionality reduction (optional, graceful fallback)
        if X.shape[0] > 10:
            try:
                import umap
                reducer = umap.UMAP(
                    n_components=min(10, X.shape[1], X.shape[0] - 2),
                    random_state=42,
                    n_jobs=1,
                )
                X = reducer.fit_transform(X)
                logger.debug("UMAP reduced embeddings to {}-d", X.shape[1])
            except Exception as exc:
                logger.debug("UMAP unavailable ({}), using raw embeddings", exc)

        gmm = GaussianMixture(
            n_components=min(n_clusters, X.shape[0]),
            random_state=42,
            max_iter=200,
        )
        return gmm.fit_predict(X).tolist()

    def _summarise(self, texts: list[str]) -> str:
        """Summarise a cluster of texts via the configured LLM backend."""
        cfg = self._cfg
        if cfg.use_stub_llm:
            return "[stub summary] " + " | ".join(t[:40] for t in texts[:3])

        from src.core.llm import call_llm
        passages = "\n\n---\n\n".join(texts)
        prompt   = _SUM_PROMPT.format(passages=passages[:6000])

        result = call_llm(prompt=prompt, settings=cfg)
        return result.strip() or " ".join(texts[:2][:500])

    def _embed(self, text: str) -> Optional[np.ndarray]:
        """Embed a summary using Jina v3 (or return None in stub mode)."""
        cfg = self._cfg
        if cfg.use_stub_llm:
            rng = np.random.default_rng(seed=abs(hash(text)) % (2**31))
            vec = rng.random(cfg.embedding_dim).astype(np.float32)
            return vec / (np.linalg.norm(vec) + 1e-9)

        try:
            from src.pdf_ingestion.embedder import get_embedder
            embedder = get_embedder(cfg)
            return embedder.embed_query(text)
        except Exception as exc:
            logger.warning("Embedding summary failed: {}", exc)
            return None
