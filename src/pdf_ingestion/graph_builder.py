"""
Memgraph graph builder — Phase 3.

Graph schema
------------
Nodes:  Document, Page, Chunk, Concept
Edges:  PART_OF, ON_PAGE, MENTIONS, RELATES_TO, PREREQUISITE_OF

GraphRAG retrieval flow
-----------------------
1. Extract concepts from the user query via Llama 3.2.
2. Cypher: find Chunk nodes that MENTION those concepts.
3. Walk RELATES_TO / PREREQUISITE_OF edges to surface adjacent chunks.
4. Return ranked chunk IDs + the concept path that connected them.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

import httpx
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
        Create Document → Page → Chunk structural nodes, then extract
        Concept nodes per chunk and wire MENTIONS / RELATES_TO / PREREQUISITE_OF.
        Returns a summary of nodes and edges created.
        """
        try:
            driver = self._get_driver()
        except Exception as exc:
            logger.warning("Memgraph unavailable ({}), skipping graph build", exc)
            return {"document_nodes": 0, "chunk_nodes": 0, "concept_nodes": 0, "edges": 0}

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
                cid    = getattr(chunk, "id", None) or getattr(chunk, "chunk_id", None)
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
                    "SET c.text=$text, c.tenant_id=$tenant_id, "
                    "c.page_number=$pg, c.document_id=$doc_id",
                    id=cid, text=chunk.text[:500], tenant_id=tenant_id,
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

                # Concept extraction
                concepts = self._extract_concepts(chunk.text)
                concept_names = [c["name"] for c in concepts]

                for concept in concepts:
                    session.run(
                        "MERGE (k:Concept {name: $name}) "
                        "SET k.type=$type",
                        name=concept["name"], type=concept.get("type", "definition"),
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

                # Prerequisite edges
                for dep_pair in _extract_prerequisites(concepts):
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
            "chunk_nodes": len(chunks),
            "concept_nodes": concept_node_count,
            "edges": edge_count,
        }

    def graph_search(
        self,
        query_text: str,
        tenant_id: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Extract concepts from query → Cypher hop traversal → ranked chunk IDs.
        Returns list of {chunk_id, concept_path, hop_distance, text_preview}.
        """
        query_concepts = self._extract_query_concepts(query_text)
        if not query_concepts:
            return []

        try:
            driver = self._get_driver()
        except Exception as exc:
            logger.warning("Memgraph graph_search failed ({})", exc)
            return []

        cypher = """
        UNWIND $concepts AS concept_name
        MATCH (k:Concept {name: concept_name})
        MATCH (c:Chunk)-[:MENTIONS]->(k)
        WHERE c.tenant_id IN [$tenant_id, 'global']
        WITH c, collect(k.name) AS direct_concepts, 0 AS hop
        RETURN c.id AS chunk_id, direct_concepts AS concept_path,
               hop AS hop_distance, c.text AS text_preview
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
                    "chunk_id": r["chunk_id"],
                    "concept_path": r["concept_path"],
                    "hop_distance": r["hop_distance"],
                    "text_preview": (r["text_preview"] or "")[:200],
                }
                for r in records
            ]
        except Exception as exc:
            logger.warning("Memgraph query failed ({})", exc)
            return []

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    # -- LLM helpers -----------------------------------------------------------

    def _extract_concepts(self, chunk_text: str) -> list[dict]:
        cfg = self._cfg
        prompt = _CONCEPT_PROMPT.format(text=chunk_text[:2000])
        try:
            resp = httpx.post(
                f"{cfg.ollama_host}/api/generate",
                json={
                    "model": cfg.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1},
                },
                timeout=cfg.ollama_timeout,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "{}")
            data = json.loads(raw)
            return data.get("concepts", [])
        except Exception as exc:
            logger.debug("Concept extraction failed ({}), skipping chunk concepts", exc)
            return []

    def _extract_query_concepts(self, query_text: str) -> list[str]:
        cfg = self._cfg
        prompt = _QUERY_CONCEPT_PROMPT.format(question=query_text)
        try:
            resp = httpx.post(
                f"{cfg.ollama_host}/api/generate",
                json={
                    "model": cfg.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.1},
                },
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "{}")
            data = json.loads(raw)
            return data.get("concepts", [])
        except Exception:
            return []


def _extract_prerequisites(concepts: list[dict]) -> list[list[str]]:
    """Pull prerequisite pairs out of the concept list returned by LLM."""
    prereqs = []
    for c in concepts:
        for alias in c.get("aliases", []):
            if isinstance(alias, list) and len(alias) == 2:
                prereqs.append(alias)
    return prereqs


# -- Factory -------------------------------------------------------------------

def get_graph_builder(
    settings: Settings | None = None,
) -> StubGraphBuilder | GraphBuilder:
    cfg = settings or get_settings()
    if cfg.use_stub_graph:
        return StubGraphBuilder()
    builder = GraphBuilder(settings=cfg)
    builder.ensure_schema()
    return builder
