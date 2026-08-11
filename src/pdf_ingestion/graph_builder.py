"""
Memgraph graph builder — Phase 3.

Graph schema
------------
Nodes:  Document, Page, Chunk, Concept
Edges:  PART_OF, ON_PAGE, MENTIONS, RELATES_TO, PREREQUISITE_OF

GraphRAG retrieval flow
-----------------------
1. At query time, embed the user question with Jina v3 (same embedding already
   computed for vector search — no extra LLM call needed).
2. Cosine similarity against Concept node embeddings stored in Memgraph
   (embedded once at build time, reused on every query).
3. Walk RELATES_TO / PREREQUISITE_OF edges from matching concept nodes to
   surface Chunk nodes connected by concept relationships.
4. Return ranked chunk IDs + the concept path that connected them.

Build-time parallelism
----------------------
build_graph() extracts concepts for all chunks in parallel (ThreadPoolExecutor,
CONCEPT_GEN_WORKERS threads) before writing to Memgraph. Ollama calls are
IO-bound so threads provide real concurrency — same pattern as card_generator.py.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from loguru import logger

from src.core.config import Settings, get_settings


# -- Concept extraction prompt -------------------------------------------------

_CONCEPT_PROMPT = """\
Extract key educational concepts from the following text. \
Return ONLY valid JSON with no markdown fences.

TEXT:
{text}

Return exactly this structure:
{{
  "concepts": [
    {{"name": "concept name", "type": "law|theorem|quantity|formula|process|phenomenon|definition|experiment|person", "aliases": ["alt name"]}}
  ],
  "prerequisites": [
    ["concept_A_depends_on", "concept_B_prerequisite"]
  ]
}}

Rules:
- Extract 3-7 most important concepts only.
- aliases can be an empty list.
- prerequisites: concept_A cannot be understood without concept_B.
"""

_QUERY_CONCEPT_PROMPT = """\
Extract the key physics/science concepts from this question. \
Return ONLY valid JSON with no markdown fences.

QUESTION: {question}

Return:
{{"concepts": ["concept1", "concept2"]}}
"""


# -- Stub (no Memgraph needed for tests) ---------------------------------------

class StubGraphBuilder:
    """In-memory graph stub — identical interface, no Bolt connection."""

    def __init__(self) -> None:
        self._chunks: dict[str, dict] = {}      # chunk_id -> {text, tenant_id, page_no}
        self._concepts: dict[str, set] = {}      # chunk_id -> set of concept names
        self._schema_ready = True

    def ensure_schema(self) -> None:
        pass

    def build_graph(
        self,
        document_id: str,
        tenant_id: str,
        chunks: list,
        doc_title: str = "",
        doc_subject: str = "",
    ) -> dict:
        node_count = 0
        for chunk in chunks:
            cid = getattr(chunk, "id", None) or getattr(chunk, "chunk_id", None)
            self._chunks[cid] = {
                "text": chunk.text,
                "tenant_id": tenant_id,
                "page_number": chunk.page_number,
                "document_id": document_id,
            }
            concepts = [f"stub_concept_{i}" for i in range(3)]
            self._concepts[cid] = set(concepts)
            node_count += len(concepts)
        return {
            "document_nodes": 1,
            "chunk_nodes": len(chunks),
            "concept_nodes": node_count,
            "edges": len(chunks) * 3,
        }

    def graph_search(
        self,
        query_text: str,
        tenant_id: str,
        query_vector: Optional[np.ndarray] = None,
        limit: int = 5,
    ) -> list[dict]:
        results = []
        for chunk_id, info in list(self._chunks.items())[:limit]:
            if info.get("tenant_id") == tenant_id or info.get("tenant_id") == "global":
                results.append({
                    "chunk_id": chunk_id,
                    "concept_path": ["stub_concept_0"],
                    "hop_distance": 1,
                    "text_preview": info["text"][:100],
                })
        return results

    def document_exists(self, document_id: str) -> bool:
        return any(
            info.get("document_id") == document_id
            for info in self._chunks.values()
        )

    def close(self) -> None:
        pass


# -- Real Memgraph builder -----------------------------------------------------

class GraphBuilder:
    """Builds and queries the concept graph in Memgraph via Bolt."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._cfg = settings or get_settings()
        self._driver = None

    def _get_driver(self):
        if self._driver is None:
            from neo4j import GraphDatabase
            uri = f"bolt://{self._cfg.memgraph_host}:{self._cfg.memgraph_port}"
            self._driver = GraphDatabase.driver(
                uri,
                auth=(self._cfg.memgraph_user, self._cfg.memgraph_password),
            )
        return self._driver

    def ensure_schema(self) -> None:
        """Create indexes and uniqueness constraints (idempotent)."""
        constraints = [
            "CREATE CONSTRAINT ON (d:Document) ASSERT d.id IS UNIQUE",
            "CREATE CONSTRAINT ON (c:Chunk) ASSERT c.id IS UNIQUE",
            "CREATE CONSTRAINT ON (k:Concept) ASSERT k.name IS UNIQUE",
            "CREATE INDEX ON :Chunk(tenant_id)",
            "CREATE INDEX ON :Chunk(document_id)",
            "CREATE INDEX ON :Concept(type)",
        ]
        try:
            with self._get_driver().session() as session:
                for cypher in constraints:
                    try:
                        session.run(cypher)
                    except Exception:
                        pass  # constraint already exists
            logger.info("Memgraph: schema ready")
        except Exception as exc:
            logger.warning("Memgraph schema setup failed ({})", exc)

    def build_graph(
        self,
        document_id: str,
        tenant_id: str,
        chunks: list,
        doc_title: str = "",
        doc_subject: str = "",
    ) -> dict:
        """
        Two-phase build:
          Phase A — extract concepts for all chunks in parallel (Ollama, IO-bound).
          Phase B — write all nodes + edges to Memgraph (sequential Cypher).

        Separating the phases means CONCEPT_GEN_WORKERS threads can saturate
        Ollama while Memgraph writes stay single-session and conflict-free.
        """
        try:
            driver = self._get_driver()
        except Exception as exc:
            logger.warning("Memgraph unavailable ({}), skipping graph build", exc)
            return {"document_nodes": 0, "chunk_nodes": 0, "concept_nodes": 0, "edges": 0}

        # ── Phase A: parallel concept extraction ──────────────────────────────
        workers = self._cfg.concept_gen_workers
        logger.info(
            "Extracting concepts for {} chunks with {} parallel workers…",
            len(chunks), workers,
        )
        chunk_concepts: dict[str, dict] = {}   # cid → {"concepts": [...], "prerequisites": [...]}
        failed = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_cid = {
                executor.submit(
                    self._extract_concepts,
                    chunk.text,
                ): getattr(chunk, "id", None) or getattr(chunk, "chunk_id", None)
                for chunk in chunks
            }
            for future in as_completed(future_to_cid):
                cid = future_to_cid[future]
                try:
                    chunk_concepts[cid] = future.result()
                    done = len(chunk_concepts)
                    if done % 500 == 0:
                        logger.debug("Concept extraction progress: {}/{}", done, len(chunks))
                except Exception as exc:
                    failed += 1
                    chunk_concepts[cid] = {"concepts": [], "prerequisites": []}
                    logger.warning("Concept extraction failed for chunk {} ({})", cid[:8], exc)

        logger.success(
            "Concept extraction done: {} chunks, {} failed",
            len(chunks), failed,
        )

        # ── Phase A.5: embed unique concept names (once, reused at query time) ─
        # Collect unique names across all chunks
        unique_concept_names: list[str] = []
        seen: set[str] = set()
        for extracted in chunk_concepts.values():
            for c in extracted.get("concepts", []):
                name = c.get("name", "")
                if name and name not in seen:
                    unique_concept_names.append(name)
                    seen.add(name)

        concept_embeddings: dict[str, list[float]] = {}
        if unique_concept_names and not self._cfg.use_stub_embedder:
            try:
                from src.pdf_ingestion.embedder import get_embedder
                embedder = get_embedder(self._cfg)
                logger.info(
                    "Embedding {} unique concept names for graph search…",
                    len(unique_concept_names),
                )
                for name in unique_concept_names:
                    vec = embedder.embed_query(name)
                    if vec is not None:
                        concept_embeddings[name] = vec.tolist()
                logger.debug(
                    "Concept embeddings ready: {}/{}",
                    len(concept_embeddings), len(unique_concept_names),
                )
            except Exception as exc:
                logger.warning(
                    "Concept embedding failed ({}); graph search will fall back to LLM", exc
                )
        concept_node_count = 0
        edge_count = 0

        with driver.session() as session:
            # Document node
            session.run(
                "MERGE (d:Document {id: $id}) "
                "SET d.title=$title, d.subject=$subject, d.tenant_id=$tenant_id",
                id=document_id, title=doc_title, subject=doc_subject, tenant_id=tenant_id,
            )

            pages_seen: set[int] = set()
            for chunk in chunks:
                cid     = getattr(chunk, "id", None) or getattr(chunk, "chunk_id", None)
                page_no = chunk.page_number or 0

                # Page node (once per page)
                if page_no not in pages_seen:
                    session.run(
                        "MERGE (p:Page {document_id: $doc_id, page_number: $pg})",
                        doc_id=document_id, pg=page_no,
                    )
                    session.run(
                        "MATCH (p:Page {document_id: $doc_id, page_number: $pg}), "
                        "(d:Document {id: $doc_id}) MERGE (p)-[:PART_OF]->(d)",
                        doc_id=document_id, pg=page_no,
                    )
                    pages_seen.add(page_no)

                # Chunk node
                session.run(
                    "MERGE (c:Chunk {id: $id}) "
                    "SET c.chunk_text=$chunk_text, c.tenant_id=$tenant_id, "
                    "c.page_number=$pg, c.document_id=$doc_id",
                    id=cid, chunk_text=chunk.text[:500], tenant_id=tenant_id,
                    pg=page_no, doc_id=document_id,
                )
                session.run(
                    "MATCH (c:Chunk {id: $cid}), (d:Document {id: $did}) "
                    "MERGE (c)-[:PART_OF]->(d)",
                    cid=cid, did=document_id,
                )
                session.run(
                    "MATCH (c:Chunk {id: $cid}), "
                    "(p:Page {document_id: $did, page_number: $pg}) "
                    "MERGE (c)-[:ON_PAGE]->(p)",
                    cid=cid, did=document_id, pg=page_no,
                )
                edge_count += 2

                # Concept nodes + edges (using pre-extracted results)
                extracted     = chunk_concepts.get(cid, {"concepts": [], "prerequisites": []})
                concepts      = extracted.get("concepts", [])
                prerequisites = extracted.get("prerequisites", [])
                concept_names = [c["name"] for c in concepts if isinstance(c, dict) and "name" in c]

                for concept in concepts:
                    session.run(
                        "MERGE (k:Concept {name: $name}) "
                        "SET k.type=$type, k.embedding=$embedding",
                        name=concept["name"],
                        type=concept.get("type", "definition"),
                        embedding=concept_embeddings.get(concept["name"]),
                    )
                    session.run(
                        "MATCH (c:Chunk {id: $cid}), (k:Concept {name: $name}) "
                        "MERGE (c)-[:MENTIONS]->(k)",
                        cid=cid, name=concept["name"],
                    )
                    concept_node_count += 1
                    edge_count += 1

                # Co-occurrence RELATES_TO edges
                for i, a in enumerate(concept_names):
                    for b in concept_names[i + 1:]:
                        session.run(
                            "MATCH (ka:Concept {name: $a}), (kb:Concept {name: $b}) "
                            "MERGE (ka)-[r:RELATES_TO]-(kb) "
                            "ON CREATE SET r.weight = 1 "
                            "ON MATCH SET r.weight = r.weight + 1",
                            a=a, b=b,
                        )
                        edge_count += 1

                # Prerequisite edges from the top-level "prerequisites" key
                for dep_pair in prerequisites:
                    if len(dep_pair) == 2:
                        session.run(
                            "MATCH (ka:Concept {name: $a}), (kb:Concept {name: $b}) "
                            "MERGE (ka)-[:PREREQUISITE_OF]->(kb)",
                            a=dep_pair[0], b=dep_pair[1],
                        )
                        edge_count += 1

        logger.info(
            "Memgraph: {} chunk nodes, {} concept nodes, {} edges for doc {}",
            len(chunks), concept_node_count, edge_count, document_id,
        )
        return {
            "document_nodes": 1,
            "chunk_nodes":    len(chunks),
            "concept_nodes":  concept_node_count,
            "edges":          edge_count,
        }

    def document_exists(self, document_id: str) -> bool:
        try:
            with self._get_driver().session() as session:
                result = session.run(
                    "MATCH (d:Document {id: $id}) RETURN count(d) AS n",
                    id=document_id,
                ).single()
                return bool(result and result["n"] > 0)
        except Exception:
            return False

    def graph_search(
        self,
        query_text: str,
        tenant_id: str,
        query_vector: Optional[np.ndarray] = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Find chunks via concept graph traversal.

        If query_vector is provided (already computed for vector search) it is
        used to rank concept nodes by cosine similarity — no LLM call needed.
        Falls back to LLM concept extraction when query_vector is absent.

        Returns list of {chunk_id, concept_path, hop_distance, text_preview}.
        """
        try:
            driver = self._get_driver()
        except Exception as exc:
            logger.warning("Memgraph graph_search failed to connect: {}", exc)
            return []

        if query_vector is not None:
            query_concepts = self._find_concepts_by_embedding(
                query_vector, tenant_id, driver, top_k=8
            )
        else:
            query_concepts = self._extract_query_concepts(query_text)

        if not query_concepts:
            return []

        cypher = """
        UNWIND $concepts AS concept_name
        MATCH (k:Concept {name: concept_name})
        MATCH (c:Chunk)-[:MENTIONS]->(k)
        WHERE c.tenant_id IN [$tenant_id, 'global']
        WITH c, collect(k.name) AS direct_concepts, 0 AS hop
        RETURN c.id AS chunk_id, direct_concepts AS concept_path,
               hop AS hop_distance, c.chunk_text AS text_preview
        LIMIT $limit
        """
        try:
            with driver.session() as session:
                records = session.run(
                    cypher,
                    concepts=query_concepts,
                    tenant_id=tenant_id,
                    limit=limit,
                ).data()
            return [
                {
                    "chunk_id":     r["chunk_id"],
                    "concept_path": r["concept_path"],
                    "hop_distance": r["hop_distance"],
                    "text_preview": (r["text_preview"] or "")[:200],
                }
                for r in records
            ]
        except Exception as exc:
            logger.warning("Memgraph query failed: {}", exc)
            return []

    def _find_concepts_by_embedding(
        self,
        query_vector: np.ndarray,
        tenant_id: str,
        driver,
        top_k: int = 8,
    ) -> list[str]:
        """
        Rank concept nodes by cosine similarity to the query vector.
        Fetches the top-mentioned concepts for this tenant (capped at 500 to
        keep the similarity computation fast), then scores them in Python.
        No LLM call — uses the Jina embedding already computed for vector search.
        """
        try:
            with driver.session() as session:
                records = session.run(
                    """
                    MATCH (c:Chunk)-[:MENTIONS]->(k:Concept)
                    WHERE c.tenant_id IN [$tenant_id, 'global']
                      AND k.embedding IS NOT NULL
                    WITH k, count(c) AS mentions
                    ORDER BY mentions DESC
                    LIMIT 500
                    RETURN k.name AS name, k.embedding AS embedding
                    """,
                    tenant_id=tenant_id,
                ).data()
        except Exception as exc:
            logger.warning("Concept embedding fetch failed: {}", exc)
            return []

        if not records:
            return []

        q = np.array(query_vector, dtype=np.float32)
        q = q / (np.linalg.norm(q) + 1e-9)

        scored: list[tuple[str, float]] = []
        for r in records:
            emb = r.get("embedding")
            if not emb:
                continue
            v = np.array(emb, dtype=np.float32)
            v = v / (np.linalg.norm(v) + 1e-9)
            scored.append((r["name"], float(np.dot(q, v))))

        scored.sort(key=lambda x: -x[1])
        top = [name for name, _ in scored[:top_k]]
        logger.debug("Concept embedding search: top={}", top)
        return top

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    # -- LLM helpers -----------------------------------------------------------

    def _extract_concepts(self, chunk_text: str) -> dict:
        from src.core.llm import call_llm
        prompt = _CONCEPT_PROMPT.format(text=chunk_text[:2000])
        try:
            raw  = call_llm(prompt=prompt, settings=self._cfg, json_mode=True)
            data = json.loads(raw) if raw else {}
            return {
                "concepts":      data.get("concepts", []),
                "prerequisites": data.get("prerequisites", []),
            }
        except Exception as exc:
            logger.debug("Concept extraction failed ({}), skipping chunk concepts", exc)
            return {"concepts": [], "prerequisites": []}

    def _extract_query_concepts(self, query_text: str) -> list[str]:
        from src.core.llm import call_llm
        prompt = _QUERY_CONCEPT_PROMPT.format(question=query_text)
        try:
            raw  = call_llm(prompt=prompt, settings=self._cfg,
                            timeout=30, json_mode=True)
            data = json.loads(raw) if raw else {}
            return data.get("concepts", [])
        except Exception:
            return []


def _extract_prerequisites(concepts: list[dict]) -> list[list[str]]:
    prereqs = []
    for c in concepts:
        for alias in c.get("aliases", []):
            if isinstance(alias, list) and len(alias) == 2:
                prereqs.append(alias)
    return prereqs


# -- Singleton factory ---------------------------------------------------------
# Avoids re-creating the Bolt connection and re-running ensure_schema() on
# every search query. Reset with reset_graph_builder() in tests.

_graph_builder_instance: StubGraphBuilder | GraphBuilder | None = None


def get_graph_builder(
    settings: Settings | None = None,
) -> StubGraphBuilder | GraphBuilder:
    global _graph_builder_instance
    if _graph_builder_instance is None:
        cfg = settings or get_settings()
        if cfg.use_stub_graph:
            _graph_builder_instance = StubGraphBuilder()
        else:
            builder = GraphBuilder(settings=cfg)
            builder.ensure_schema()
            _graph_builder_instance = builder
    return _graph_builder_instance


def reset_graph_builder() -> None:
    """Close and clear the singleton — used in tests and after config changes."""
    global _graph_builder_instance
    if _graph_builder_instance is not None:
        _graph_builder_instance.close()
        _graph_builder_instance = None
