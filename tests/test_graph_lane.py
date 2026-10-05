"""Graph-lane robustness: a down Memgraph must fail fast, not block.

`graph_builder._get_driver()` used to build its own neo4j driver with no
`connection_timeout`, ignoring `database.get_memgraph()`, which sets
`connection_timeout=3` for exactly this reason. On the cluster (where
`concept_embeddings` is populated) `graph_search` reaches `driver.session()` for
every multihop query, so an un-timed driver meant each query blocked on the neo4j
default (~30s) instead of failing in 3s.

Locally `concept_embeddings` is empty, so `graph_search` early-returns before the
Memgraph query — which is why these tests force a non-empty concept list.
"""
from __future__ import annotations

import time

import numpy as np

from src.core.config import Settings
from src.core.database import reset_singletons
from src.pdf_ingestion.graph_builder import GraphBuilder

def _dead_settings() -> Settings:
    # 10.255.255.1 black-holes SYNs, so a connect attempt exercises
    # connection_timeout (a closed 127.0.0.1 port would refuse instantly
    # instead, and the test would pass even with no timeout configured).
    return Settings(use_stub_graph=False, memgraph_host="10.255.255.1", memgraph_port=7687)


def _builder() -> GraphBuilder:
    reset_singletons()
    return GraphBuilder(_dead_settings())


def test_graph_search_fails_fast_when_memgraph_unreachable(monkeypatch):
    """With the fix, graph_search returns [] in ~3s; without it, ~30s+."""
    builder = _builder()
    # Force a non-empty concept list so graph_search reaches the Memgraph query
    # instead of early-returning on the (empty, local) Qdrant concept collection.
    monkeypatch.setattr(builder, "_find_concepts_by_embedding", lambda v, top_k=8: ["force"])

    t0 = time.monotonic()
    out = builder.graph_search(
        "why does a satellite stay in orbit?",
        "global",
        query_vector=np.zeros(768, dtype=np.float32),
        limit=3,
    )
    elapsed = time.monotonic() - t0

    assert out == []
    assert elapsed < 10, f"graph_search blocked {elapsed:.1f}s — connection_timeout not applied"


def test_graph_builder_reuses_the_timed_driver_factory():
    """_get_driver must delegate to get_memgraph (the single source of the timeout)."""
    from src.core.database import get_memgraph

    reset_singletons()
    cfg = _dead_settings()
    builder = GraphBuilder(cfg)
    assert builder._get_driver() is get_memgraph(cfg)
