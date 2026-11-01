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
from src.pdf_ingestion.graph_checkpoint import GraphCheckpoint, prompt_digest


def _chunk_id(chunk) -> str:
    """The chunk's id, whichever attribute its class exposes.

    Chunk identity is read in several places in this module and the two attribute names
    (``id`` on the SQLite model, ``chunk_id`` on ``TextChunk``) were previously re-derived at
    each site — which is how a checkpoint key and a graph node id can silently disagree. Raising
    on a chunk with neither keeps that from becoming a silent ``None`` key.
    """
    cid = getattr(chunk, "id", None) or getattr(chunk, "chunk_id", None)
    if cid is None:
        raise ValueError(f"chunk {chunk!r} exposes neither 'id' nor 'chunk_id'")
    return str(cid)


# -- Concept extraction prompt -------------------------------------------------

_CONCEPT_PROMPT = """\
Extract the most important physics/science concepts from the text below.
Return ONLY valid JSON with no markdown fences.

TEXT:
{text}

Return exactly this structure:
{{
  "concepts": [
    {{"name": "concept name", "type": "law|theorem|quantity|formula|process|phenomenon|definition|experiment|person", "aliases": ["alt name"]}}
  ],
  "prerequisites": [
    ["concept_A_name", "concept_B_name"]
  ]
}}

Rules:
- Extract 3-7 concepts maximum. Prefer fewer, higher-quality concepts over many vague ones.
- Use the canonical full name (e.g. "Newton's Second Law" not "F=ma"; "kinetic energy" not "KE").
- Type must be one of: law, theorem, quantity, formula, process, phenomenon, definition, experiment, person.
- aliases: alternative names or symbols (e.g. ["F=ma", "second law"]). Empty list if none.
- prerequisites: [A, B] means concept A cannot be understood without concept B.
  Only list genuine conceptual dependencies, not superficial associations.
- Only extract concepts explicitly discussed in the text. Do not infer from context.
"""

_QUERY_CONCEPT_PROMPT = """\
Extract the key physics/science concepts being asked about in this question.
Return ONLY valid JSON with no markdown fences.

QUESTION: {question}

Return:
{{"concepts": ["canonical concept name 1", "canonical concept name 2"]}}

Rules:
- Use canonical names (e.g. "Newton's First Law" not "inertia law").
- 1-4 concepts only. Omit vague terms like "physics" or "science".
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
        resume: bool = True,
    ) -> dict:
        node_count = 0
        for chunk in chunks:
            cid = _chunk_id(chunk)
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
            # Signature parity with the real builder: the stub has no LLM, so nothing can fail.
            "failed_chunks": 0,
            "chunks_resumed": 0,
            "checkpoint_path": None,
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
        # §I96 — the graph lane also swallows its failure (`graph_search` returns [] when Memgraph
        # is unreachable), so a multihop arm can silently run without its lane. Count it.
        self.graph_dropouts: int = 0
        self.last_graph_dropout: str | None = None

    def _get_driver(self):
        """Return the shared Memgraph driver.

        Delegates to ``database.get_memgraph``, which sets ``connection_timeout=3``.
        This module used to build its own driver with no timeout, so a down
        Memgraph blocked every multihop query on the neo4j default and made a
        whole eval run look like it had hung (123s stubbed vs >420s hung).
        """
        if self._driver is None:
            from src.core.database import get_memgraph
            driver = get_memgraph(self._cfg)
            if driver is None:
                raise RuntimeError("Memgraph driver unavailable (see get_memgraph)")
            self._driver = driver
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
        resume: bool = True,
    ) -> dict:
        """
        Two-phase build:
          Phase A — extract concepts for all chunks in parallel (Ollama, IO-bound).
          Phase B — write all nodes + edges to Memgraph (sequential Cypher).

        Separating the phases means CONCEPT_GEN_WORKERS threads can saturate
        Ollama while Memgraph writes stay single-session and conflict-free.

        Phase A is **checkpointed** (§I23): each completed extraction is appended to
        ``data/graph_cache/<doc8>__<key>.jsonl`` and a re-run skips what is done. The
        2026-10-19 build took 16 h 25 m and held every extraction in RAM until the end, so an
        abort discarded all of it. ``resume=False`` discards the checkpoint and re-extracts
        everything. A chunk whose extraction FAILED is not treated as done — it is re-attempted.

        The returned stats carry **``failed_chunks``**, the count of chunks that contributed no
        concepts because their extraction call failed. That count — not the old ``failed`` local,
        which stayed 0 for all 44 failures of that build — is the phase's exit criterion.
        """
        try:
            driver = self._get_driver()
        except Exception as exc:
            logger.warning("Memgraph unavailable ({}), skipping graph build", exc)
            return {"document_nodes": 0, "chunk_nodes": 0, "concept_nodes": 0, "edges": 0}

        # ── Loud dimension guard, BEFORE the expensive half (§I12/§I47) ────────
        # Checked here rather than at the upsert, because the upsert happens AFTER concept
        # extraction — a multi-hour half — and a stale collection would waste all of it.
        if not self._cfg.use_stub_embedder:
            from src.core.database import get_qdrant
            self._assert_collection_dim(
                get_qdrant(self._cfg), self._cfg.concept_collection, self._cfg.dense_dim
            )

        # ── Phase A: parallel concept extraction, CHECKPOINTED (§I23) ──────────
        workers = self._cfg.concept_gen_workers

        # A side-car checkpoint, as the card phase has (§I27): Memgraph stays the single write
        # point, and this only persists the extraction output so an abort costs the chunks since
        # the last checkpoint rather than the whole run.
        checkpoint = None
        if getattr(self._cfg, "graph_checkpoint_enabled", True):
            try:
                checkpoint = GraphCheckpoint.open(
                    directory=getattr(self._cfg, "graph_checkpoint_dir", "./data/graph_cache"),
                    document_id=document_id,
                    chunk_ids=[_chunk_id(c) for c in chunks],
                    model=self._extraction_model(),
                    prompt_digest_=prompt_digest(_CONCEPT_PROMPT),
                    fresh=not resume,
                )
            except Exception as exc:  # a broken checkpoint must not lose the run
                logger.warning("Graph checkpoint unavailable ({}): continuing without one", exc)
                checkpoint = None

        chunk_concepts: dict[str, dict] = {}
        if checkpoint is not None:
            chunk_concepts.update(checkpoint.extractions)
        pending = [c for c in chunks if checkpoint is None or _chunk_id(c) not in checkpoint.done]
        every_n = int(getattr(self._cfg, "graph_checkpoint_every", 25))

        logger.info(
            "Extracting concepts for {} of {} chunks with {} parallel workers — {} already "
            "checkpointed{}",
            len(pending), len(chunks), workers, len(chunks) - len(pending),
            f" [{checkpoint.path.name}]" if checkpoint is not None else " [no checkpoint]",
        )

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_chunk = {executor.submit(self._extract_concepts, c.text): c for c in pending}
            for future in as_completed(future_to_chunk):
                chunk = future_to_chunk[future]
                cid = _chunk_id(chunk)
                try:
                    result = future.result()
                except Exception as exc:  # the extractor swallows its own errors; belt and braces
                    result = {"concepts": [], "prerequisites": [], "ok": False, "error": str(exc)}
                chunk_concepts[cid] = result
                if checkpoint is not None:
                    # Recorded whether it succeeded or failed; a FAILED one is written with
                    # ok=false so a resume re-attempts it instead of baking the loss in (§I23).
                    checkpoint.record(cid, getattr(chunk, "chunk_index", 0) or 0, result)
                    if checkpoint.due(every_n, 60.0):
                        checkpoint.note_flushed()
                        logger.info(
                            "Concept extraction: {}/{} done …", len(chunk_concepts), len(chunks),
                        )

        if checkpoint is not None:
            checkpoint.close()

        # The count that matters (§I23 defect 2). The old `failed` local only incremented when the
        # future itself raised, and `_extract_concepts` swallows every exception — so 44 real
        # failures on the 2026-10-19 build were reported as "0 failed".
        failed_chunks = sum(1 for r in chunk_concepts.values() if not r.get("ok", False))
        logger.success(
            "Concept extraction done: {} chunks, {} FAILED (contributed no concepts)",
            len(chunks), failed_chunks,
        )
        if failed_chunks:
            logger.warning(
                "{} chunk(s) contributed NO concepts because their extraction call failed — "
                "retry these, and read THIS count rather than the absence of an error line "
                "(IMPROVEMENTS.md §I23).",
                failed_chunks,
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
                # The DENSE lane (§I12). These vectors rank Concept nodes in
                # ``concept_embeddings``, and the query side reaches them with the same dense
                # vector the KB lanes use — so both sides must be the dense space. They were
                # built by the retired local 768d Nomic embedder, which is why the collection
                # was 768d while every query against it was 1024d; that mismatch is what made
                # the graph lane return nothing at all in `evaluate_rag.py` (§I47).
                # ``embed_query`` on BOTH sides is deliberate and unchanged: it keeps the index
                # and the query in one space. Whether concept NAMES should be embedded as
                # passages (``embed_documents``) instead is a separate, unmeasured question —
                # not bundled into a lane migration.
                from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
                embedder = get_cluster_embedder(self._cfg)
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

        # ── Phase A.6: upsert concept embeddings to Qdrant ────────────────────
        # This is what makes query-time concept lookup fast (~5ms ANN search
        # instead of fetching hundreds of embeddings from Memgraph over Bolt).
        if concept_embeddings:
            self._upsert_concepts_to_qdrant(
                concept_embeddings=concept_embeddings,
                chunk_concepts=chunk_concepts,
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
            # NB: this counts (chunk, concept) MENTIONS pairs, not distinct concepts — the label
            # is wrong and is a separate register item (§I22). Do not read it as a concept count.
            "concept_nodes":  concept_node_count,
            "edges":          edge_count,
            # §I23: the honest extraction outcome. `failed_chunks` is the phase's exit criterion.
            "failed_chunks":  failed_chunks,
            "chunks_resumed": len(chunks) - len(pending),
            "checkpoint_path": str(checkpoint.path) if checkpoint is not None else None,
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
            # §I96 — COUNT it: a multihop arm that silently ran without its lane is not the
            # treatment, and nothing outside the log text could see it before this.
            self.graph_dropouts += 1
            self.last_graph_dropout = f"{type(exc).__name__}: {exc}"
            logger.error(
                "GRAPH SEARCH UNAVAILABLE — Memgraph connect failed ({}); the "
                "multihop lane returns no results [dropout #{}]", exc, self.graph_dropouts,
            )
            return []

        if query_vector is not None:
            scored_concepts = self._find_concepts_scored(query_vector, top_k=8,
                                                         query_text=query_text)
        else:
            scored_concepts = [(n, 1.0) for n in self._extract_query_concepts(query_text)]

        if not scored_concepts:
            return []

        # Rank by how many DISTINCT query concepts a chunk matches, then by how
        # similar those concepts are to the query. Without any ORDER BY this
        # returned an arbitrary LIMIT — Memgraph's storage order — so a question
        # about satellite orbits came back with chunks that merely mention "orbit"
        # (aberration, telescope tilt). Note this is a single-hop concept lookup:
        # no traversal happens, which is why hop_distance is the constant 0 and is
        # no longer surfaced to the user as "hops".
        cypher = """
        UNWIND $concepts AS c
        MATCH (k:Concept {name: c.name})
        MATCH (ch:Chunk)-[:MENTIONS]->(k)
        WHERE ch.tenant_id IN [$tenant_id, 'global']
        WITH ch, collect(DISTINCT k.name) AS matched, sum(c.score) AS concept_score
        RETURN ch.id AS chunk_id, matched AS concept_path,
               size(matched) AS matched_concepts, concept_score,
               ch.chunk_text AS text_preview
        ORDER BY matched_concepts DESC, concept_score DESC
        LIMIT $limit
        """
        try:
            with driver.session() as session:
                records = session.run(
                    cypher,
                    concepts=[{"name": n, "score": s} for n, s in scored_concepts],
                    tenant_id=tenant_id,
                    limit=limit,
                ).data()
            return [
                {
                    "chunk_id":     r["chunk_id"],
                    "concept_path": r["concept_path"],
                    "matched_concepts": r["matched_concepts"],
                    "concept_score": r["concept_score"],
                    "hop_distance": 0,   # single-hop by construction; see above
                    "text_preview": (r["text_preview"] or "")[:200],
                }
                for r in records
            ]
        except Exception as exc:
            logger.error(
                "GRAPH SEARCH FAILED — Memgraph query error ({}); the multihop "
                "lane returns no results", exc,
            )
            return []

    @staticmethod
    def _assert_collection_dim(qdrant, collection: str, dim: int) -> None:
        """Fail loudly, naming the fix, when a collection's dimension no longer matches.

        `concept_embeddings` and `derivative_artifacts` were created at the retired 768d
        `embedding_dim`; they are now created at `dense_dim` (§I12). Qdrant **cannot** resize a
        collection in place, so a store built before the move keeps a 768d collection and every
        1024d write or query against it is rejected.

        Without this check the only symptom is a bare `400 Bad Request` from Qdrant, which reads
        as a transport error rather than a stale schema. That is precisely how §I47 went
        unnoticed: the graph lane returned nothing on every multihop query in
        `scripts/evaluate_rag.py` for a week, visible only as a WARNING line per query.
        """
        try:
            vectors = qdrant.get_collection(collection).config.params.vectors
            size = getattr(vectors, "size", None)
        except Exception:
            return              # absent, or a named-vector layout — ensure_* handles creation
        if size is not None and int(size) != int(dim):
            raise RuntimeError(
                f"collection '{collection}' is {size}d but this run embeds {dim}d. It predates "
                f"the dense-lane move (IMPROVEMENTS.md §I12) and Qdrant cannot resize a "
                f"collection in place. Nothing was written. Drop it and re-run — e.g. "
                f"`uv run python scripts/reset_for_reingest.py --yes`, which deletes "
                f"'{collection}' along with the other derived collections, or delete just this "
                f"collection to keep the rest."
            )

    def _upsert_concepts_to_qdrant(
        self,
        concept_embeddings: dict[str, list[float]],
        chunk_concepts: dict[str, dict],
    ) -> None:
        """Upsert concept embeddings to Qdrant for fast ANN search at query time."""
        import uuid as _uuid
        from qdrant_client.models import PointStruct
        from src.core.database import get_qdrant

        qdrant = get_qdrant(self._cfg)

        # Collect concept type from extracted data
        concept_types: dict[str, str] = {}
        for extracted in chunk_concepts.values():
            for c in extracted.get("concepts", []):
                name = c.get("name", "")
                if name and name not in concept_types:
                    concept_types[name] = c.get("type", "definition")

        points = []
        for name, embedding in concept_embeddings.items():
            # Deterministic point ID from concept name — ensures upsert is idempotent
            point_id = str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"concept:{name}"))
            points.append(PointStruct(
                id=point_id,
                vector=embedding,
                payload={
                    "name": name,
                    "type": concept_types.get(name, "definition"),
                },
            ))

        # Upsert in batches of 256
        for i in range(0, len(points), 256):
            qdrant.upsert(
                collection_name=self._cfg.concept_collection,
                points=points[i : i + 256],
            )
        logger.info(
            "Upserted {} concept embeddings to Qdrant collection '{}'",
            len(points), self._cfg.concept_collection,
        )

    def _find_concepts_scored(
        self,
        query_vector: np.ndarray,
        top_k: int = 8,
        query_text: str | None = None,
    ) -> list[tuple[str, float]]:
        """Top-k concepts by similarity to the query, WITH their scores.

        The scores are the point. Without them the graph lane can only rank by how
        many concept names a chunk matches — and the concept vocabulary holds
        near-duplicates ('orbit' / 'Orbit' / 'planetary orbit' / 'Planetary Orbit',
        "Earth's orbit" / "Earth's orbital motion") that are separate Concept nodes,
        so almost every chunk ties at 1 and an ORDER BY cannot discriminate. Ranking
        on the similarity of the best-matched concept does.

        ⚠️ §A — the query must be in the CONCEPT collection's space. `concept_embeddings` was built
        at 768 (§I83) while an arm's dense model may be 1024; handing the arm's vector straight to
        Qdrant 400s and the lane silently returned []. `query_text` (the RAW query) lets the lane be
        re-embedded in the collection's space; a mismatch with no text RAISES (§A guard A4).
        """
        try:
            from src.core.database import get_qdrant
            qdrant = get_qdrant(self._cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Concept Qdrant client unavailable ({}), falling back to LLM", exc)
            return []
        # ⚠️ §A — resolved OUTSIDE the query's `try`: a dimension mismatch must RAISE (guard A4),
        # not be swallowed into an empty lane by the fallback below.
        from src.pdf_ingestion.store import resolve_space_query_vector
        qv = resolve_space_query_vector(self._cfg, qdrant, query_vector, query_text,
                                        self._cfg.concept_collection, "graph")
        if qv is None:          # unreachable: the caller always supplies the arm's vector
            raise RuntimeError("§A: the 'graph' lane has no query vector to send")
        try:
            response = qdrant.query_points(
                collection_name=self._cfg.concept_collection,
                query=qv.tolist(),
                limit=top_k,
                with_payload=True,
            )
            scored: list[tuple[str, float]] = []
            for p in response.points:
                payload = p.payload or {}
                name = payload.get("name")
                if name:
                    scored.append((name, float(p.score)))
            logger.debug("Concept Qdrant search: top={}", [n for n, _ in scored])
            return scored
        except Exception as exc:
            logger.warning("Concept Qdrant search failed ({}), falling back to LLM", exc)
            return []

    def _find_concepts_by_embedding(
        self,
        query_vector: np.ndarray,
        top_k: int = 8,
    ) -> list[str]:
        """Concept names only — kept for callers that do not rank on similarity."""
        return [name for name, _ in self._find_concepts_scored(query_vector, top_k)]

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    # -- LLM helpers -----------------------------------------------------------

    def _extract_concepts(self, chunk_text: str) -> dict:
        """Extract concepts for one chunk.

        The result **always** carries ``ok``. ``ok=False`` means the call failed or its output was
        unusable — the LLM errored, returned nothing, or returned something that is not JSON.
        That is NOT the same as "this chunk has no concepts": valid JSON with an empty list is
        ``ok=True`` and IS a completed extraction.

        The two were indistinguishable before, which is why 44 real failures on the 2026-10-19
        build were reported as "0 failed" (§I23): the exception was swallowed into an empty
        concept list and the caller's counter never moved.
        """
        from src.core.llm import call_llm
        prompt = _CONCEPT_PROMPT.format(text=chunk_text[:2000])
        try:
            raw = call_llm(prompt=prompt, settings=self._extraction_settings(), json_mode=True)
        except Exception as exc:
            logger.debug("Concept extraction call failed ({})", exc)
            return {"concepts": [], "prerequisites": [], "ok": False, "error": str(exc)}
        if not raw:
            return {"concepts": [], "prerequisites": [], "ok": False, "error": "empty response"}
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.debug("Concept extraction returned unusable JSON ({})", exc)
            return {"concepts": [], "prerequisites": [], "ok": False,
                    "error": f"invalid JSON: {exc}"}
        if not isinstance(data, dict):
            return {"concepts": [], "prerequisites": [], "ok": False,
                    "error": f"expected a JSON object, got {type(data).__name__}"}
        return {
            "concepts":      data.get("concepts", []),
            "prerequisites": data.get("prerequisites", []),
            "ok":            True,
            "error":         None,
        }

    def _extraction_settings(self) -> Settings:
        """The settings concept extraction actually calls with (§I23(c)).

        The extractor is chosen per stage in `config.yaml` (`concept_extraction.model`) so it can
        differ from the card/RAPTOR model, which lives in `card_generation`. Read fresh on each call
        rather than cached — `pipeline_config` already caches the file, and a cached *settings*
        object here would silently survive a config edit mid-run.

        **Both** the index-time extraction (`_extract_concepts`) and the query-time one
        (`_extract_query_concepts`) go through this on purpose: if the graph is built by one model
        and a query resolves concepts with another, their naming conventions differ and the query
        misses nodes the index holds — the §G3 defect class, manufactured on purpose.

        Falls back to `.env`'s model when the section is absent, so a checkout without
        `config.yaml` behaves exactly as before.
        """
        from src.core.pipeline_config import get_section
        section = get_section("concept_extraction") or {}
        updates: dict = {}
        model = section.get("model")
        if isinstance(model, str) and model.strip():
            if self._cfg.llm_backend == "openai":
                updates["openai_model"] = model.strip()
            else:
                updates["ollama_model"] = model.strip()
        base = section.get("base_url")
        if isinstance(base, str) and base.strip() and self._cfg.llm_backend == "openai":
            updates["openai_api_base"] = base.strip()
        return self._cfg.model_copy(update=updates) if updates else self._cfg

    def _extraction_model(self) -> str:
        """The model concept extraction will actually call — part of the checkpoint's key.

        A model swap changes what an extraction means, so a checkpoint written under one model
        must not be resumed under another. This reads the SAME resolution the call uses, so the key
        cannot disagree with the model that produced the record.
        """
        cfg = self._extraction_settings()
        return (cfg.openai_model if cfg.llm_backend == "openai"
                else cfg.ollama_model)

    def _extract_query_concepts(self, query_text: str) -> list[str]:
        from src.core.llm import call_llm
        prompt = _QUERY_CONCEPT_PROMPT.format(question=query_text)
        try:
            raw  = call_llm(prompt=prompt, settings=self._extraction_settings(),
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
