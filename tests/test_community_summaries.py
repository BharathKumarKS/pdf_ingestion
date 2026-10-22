"""§G2 — the community hierarchy and its summaries, offline.

Every test uses a fake session and a fake LLM. The two load-bearing ones are V2 (every community
is internally connected — Leiden's guarantee over Louvain, which returned a disconnected
75-member community in §I33) and V6 (a leaf summary reads the FULL passage, never the graph's
500-char `Chunk.chunk_text` stub). Delete the truncation guard's absence and V6 fails; run Louvain
instead of Leiden and V2 can fail.
"""
from __future__ import annotations

from src.pdf_ingestion.community_summaries import (
    build_hierarchy,
    read_concept_chunks,
    read_concept_graph,
    summarize_communities,
)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return self._rows


class FakeSession:
    def __init__(self, names, edges=(), concept_chunks=None):
        self.names = names
        self.edges = list(edges)                    # (source, target, weight)
        self.concept_chunks = concept_chunks or {}

    def run(self, cypher, **params):
        if "RETURN DISTINCT k.name AS name" in cypher:
            return FakeResult([{"name": n} for n in self.names])
        if "RETURN k.name AS source" in cypher:
            return FakeResult(
                [{"source": s, "target": t, "weight": w} for s, t, w in self.edges]
            )
        if "collect(DISTINCT c.id) AS chunks" in cypher:
            return FakeResult([
                {"name": n, "chunks": self.concept_chunks.get(n, [])} for n in self.names
            ])
        return FakeResult([])


class FakeLLM:
    def __init__(self):
        self.prompts: list[str] = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return f"summary[{len(prompt)}]"


def _provider(mapping):
    return lambda ids: [mapping[i] for i in ids if i in mapping]


def _two_cliques():
    """Two 6-node cliques joined by one edge — Leiden should separate them at some resolution."""
    a = [f"a{i}" for i in range(6)]
    b = [f"b{i}" for i in range(6)]
    edges = []
    for group in (a, b):
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                edges.append((group[i], group[j], 1.0))
    edges.append(("a0", "b0", 1.0))
    return a + b, edges


# ── reads ─────────────────────────────────────────────────────────────────────────────────────

def test_read_concept_graph_keeps_isolated_nodes_and_edge_weight():
    session = FakeSession(["x", "y", "z"], [("x", "y", 2.5), ("y", "x", 2.5)])
    g = read_concept_graph(session, "doc1")
    assert set(g.nodes) == {"x", "y", "z"}          # z has no edge but is still a node
    assert g["x"]["y"]["weight"] == 2.5


def test_read_concept_chunks_maps_names_to_chunk_ids():
    session = FakeSession(["a", "b"], concept_chunks={"a": ["c1", "c2"], "b": []})
    assert read_concept_chunks(session, "doc1") == {"a": ["c1", "c2"], "b": []}


# ── the hierarchy ─────────────────────────────────────────────────────────────────────────────

def test_build_hierarchy_is_finest_first_and_nests():
    names, edges = _two_cliques()
    g = read_concept_graph(FakeSession(names, edges), "doc1")
    h = build_hierarchy(g, resolutions=(0.5, 1.0, 2.0))

    assert [lvl.resolution for lvl in h.levels] == [2.0, 1.0, 0.5]   # leaf = finest
    assert len(h.levels[0].communities) >= len(h.levels[-1].communities)

    # V2 — every community is internally connected at every resolution (Leiden's guarantee)
    for lvl in h.levels:
        assert lvl.connectivity["all_connected"], lvl.connectivity["disconnected"]

    # the parent link goes one level coarser and holds most of the fine community's members
    for (level, cid), (plevel, pcid) in h.parent_of.items():
        assert plevel == level + 1
        fine = h.levels[level].communities[cid]
        parent = h.levels[plevel].communities[pcid]
        assert len(fine & parent) / len(fine) >= 0.5

    assert set(h.nesting) == {0, 1}
    assert all(0.0 <= v <= 1.0 for v in h.nesting.values())


def test_build_hierarchy_is_deterministic():
    names, edges = _two_cliques()
    g = read_concept_graph(FakeSession(names, edges), "doc1")
    a = build_hierarchy(g, resolutions=(0.5, 1.0, 2.0))
    b = build_hierarchy(g, resolutions=(0.5, 1.0, 2.0))
    assert [lvl.communities for lvl in a.levels] == [lvl.communities for lvl in b.levels]


# ── summaries + the V4 cost ledger ────────────────────────────────────────────────────────────

def _hierarchy_and_chunks():
    names, edges = _two_cliques()
    concept_chunks = {n: [f"chunk-{n}"] for n in names}
    g = read_concept_graph(FakeSession(names, edges), "doc1")
    h = build_hierarchy(g, resolutions=(0.5, 1.0, 2.0))
    return h, concept_chunks


def test_dry_run_makes_no_calls_and_still_reports_prompt_sizes():
    h, concept_chunks = _hierarchy_and_chunks()
    llm = FakeLLM()
    provider = _provider({f"chunk-{n}": "passage text" for n in
                          [f"{g}{i}" for g in "ab" for i in range(6)]})
    out = summarize_communities(h, concept_chunks, provider, llm=llm, dry_run=True)

    assert llm.prompts == []                       # V4: no spend on a dry run
    assert out["total_calls"] == 0
    assert out["calls_by_level"] == {}
    assert sum(out["prompt_chars_by_level"].values()) > 0   # ...but the cost is visible
    assert all(v == "" for v in out["summaries"].values())


def test_cost_ledger_counts_every_call():
    h, concept_chunks = _hierarchy_and_chunks()
    llm = FakeLLM()
    provider = _provider({f"chunk-{n}": "passage text" for n in
                          [f"{g}{i}" for g in "ab" for i in range(6)]})
    out = summarize_communities(h, concept_chunks, provider, llm=llm, dry_run=False)

    assert out["total_calls"] == len(llm.prompts)                    # V4
    assert out["total_calls"] == sum(out["calls_by_level"].values())
    assert out["total_calls"] > 0
    assert all(v for v in out["summaries"].values())                 # every summary is non-empty


def test_communities_with_no_source_material_are_skipped_not_summarised():
    h, _ = _hierarchy_and_chunks()
    llm = FakeLLM()
    out = summarize_communities(h, {}, _provider({}), llm=llm, dry_run=False)
    assert out["total_calls"] == 0
    assert out["skipped_empty"] > 0


# ── V6: the FULL passage, not the graph's 500-char stub ───────────────────────────────────────

def test_v6_full_text_is_passed_not_the_500_char_stub():
    long_passage = "x" * 600
    names = ["a0", "a1"]
    edges = [("a0", "a1", 1.0)]
    concept_chunks = {"a0": ["c0"], "a1": []}
    g = read_concept_graph(FakeSession(names, edges), "doc1")
    h = build_hierarchy(g, resolutions=(0.5, 1.0, 2.0))

    llm = FakeLLM()
    summarize_communities(h, concept_chunks, _provider({"c0": long_passage}), llm=llm, dry_run=False)

    assert llm.prompts, "the leaf community with a chunk should have been summarised"
    assert long_passage in llm.prompts[0]           # all 600 chars — a [:500] slice fails here
    assert len(llm.prompts[0]) > 500
