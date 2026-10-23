"""§G2 — the community hierarchy and its summaries, offline.

Every test uses a fake session and a fake LLM. The two load-bearing ones are V2 (every community
is internally connected — Leiden's guarantee over Louvain, which returned a disconnected
75-member community in §I33) and V6 (a leaf summary reads the FULL passage, never the graph's
500-char `Chunk.chunk_text` stub). Delete the truncation guard's absence and V6 fails; run Louvain
instead of Leiden and V2 can fail.
"""
from __future__ import annotations

from src.pdf_ingestion.community_summaries import (
    PARENT_PROMPT,
    build_hierarchy,
    read_concept_chunks,
    read_concept_graph,
    read_concept_names,
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
        if "RETURN a.name AS a" in cypher:
            return FakeResult([{"a": a, "b": b, "w": w} for a, b, w in self.edges])
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

def test_read_concept_graph_drops_isolates_to_match_the_gate():
    """The gate builds its graph from edges only; §G2 must detect on the SAME graph.

    Measured 2026-10-22: including isolates gave 7,427 nodes / Q=0.7786, the gate's edge-only graph
    7,398 / Q=0.783332 — a different partition from the one the gate approved. Re-adding
    `g.add_node(name)` for every concept fails this test.
    """
    session = FakeSession(["x", "y", "z"], [("x", "y", 2.5), ("y", "x", 2.5)])
    g = read_concept_graph(session, "doc1")
    assert set(g.nodes) == {"x", "y"}          # z carries no RELATES_TO edge
    assert g["x"]["y"]["weight"] == 2.5
    # ...and z is not silently lost: the full vocabulary is available to count it
    assert set(read_concept_names(session, "doc1")) == {"x", "y", "z"}


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


def test_dry_run_does_not_report_parents_as_source_less():
    """A dry run's parents are empty because the CHILDREN were never generated, not for want of source.

    Measured 2026-10-22 on the live graph: the old counter reported **403** parents as "skipped (no
    source material)" — every community above the leaf level — when in fact every one of them has
    source material (its children). The pre-flight cost report therefore understated the run by 403
    calls while reading as though those communities would never be summarised. Reverting the
    `dry_run and children.get(...)` branch fails this test.
    """
    h, concept_chunks = _hierarchy_and_chunks()
    provider = _provider({f"chunk-{n}": "passage text" for n in
                          [f"{g}{i}" for g in "ab" for i in range(6)]})
    out = summarize_communities(h, concept_chunks, provider, llm=FakeLLM(), dry_run=True)

    assert out["skipped_empty"] == 0          # every leaf has source material
    assert out["deferred_parents"] > 0        # parents exist; they were not generated, not empty
    # ...and a REAL run counts the same communities as calls, not as skipped
    real = summarize_communities(h, concept_chunks, provider, llm=FakeLLM(), dry_run=False)
    assert real["deferred_parents"] == 0
    assert real["skipped_empty"] == 0
    assert real["total_calls"] == out["deferred_parents"] + len(h.levels[0].communities)


def test_a_failed_llm_call_is_counted_not_silently_an_empty_summary():
    """`call_llm` returns "" on failure, so an all-failed run must not read as a successful build.

    The §I25 class: without this counter, a run in which EVERY call failed reports a full cost
    ledger (`total_calls` = N) and writes an artifact whose summaries are all "" — a total loss that
    looks exactly like a build. Reverting `if not text.strip(): empty_returns += 1` fails this test.
    """
    h, concept_chunks = _hierarchy_and_chunks()
    provider = _provider({f"chunk-{n}": "passage text" for n in
                          [f"{g}{i}" for g in "ab" for i in range(6)]})
    failed = summarize_communities(h, concept_chunks, provider, llm=lambda p: "", dry_run=False)
    assert failed["total_calls"] > 0
    assert failed["empty_returns"] == failed["total_calls"]     # counted, not swallowed
    assert all(v == "" for v in failed["summaries"].values())

    healthy = summarize_communities(h, concept_chunks, provider, llm=FakeLLM(), dry_run=False)
    assert healthy["empty_returns"] == 0


# ── the prompt budget: a community that does not fit is summarised map-reduce ────────────────

def _long_text_hierarchy(chars_per_chunk=1600):
    names, edges = _two_cliques()
    concept_chunks = {n: [f"chunk-{n}"] for n in names}
    texts = {f"chunk-{n}": ("physics " * (chars_per_chunk // 8)) for n in names}
    g = read_concept_graph(FakeSession(names, edges), "doc1")
    h = build_hierarchy(g, resolutions=(0.5, 1.0, 2.0))
    return h, concept_chunks, texts


def test_a_community_that_does_not_fit_is_summarised_map_reduce_without_dropping_source():
    """A community whose material exceeds the prompt budget is summarised map-reduce, losslessly.

    Measured 2026-10-22: the §G2 leaf prompts run to 273,470 chars while the *graph build's* extractor
    has a 15,000-token context — and the summariser is a different model with a different one. The
    budget is therefore a parameter, and the code must handle a community that does not fit rather
    than send a prompt the server refuses (`call_llm` would return "" and the community would end up
    with no summary). Reverting `_summarise_with_batching` to a single `llm(prompt)` fails this test
    (the whole body goes in one prompt, over the budget).
    """
    h, concept_chunks, texts = _long_text_hierarchy()
    llm = FakeLLM()
    out = summarize_communities(h, concept_chunks, _provider(texts), llm=llm,
                                dry_run=False, max_prompt_chars=3000)

    assert out["batched_communities"] > 0
    assert out["map_calls"] > 0 and out["reduce_calls"] > 0
    # the ledger is COMPLETE: every call is classified as single, map or reduce
    assert out["total_calls"] == len(llm.prompts)
    assert out["total_calls"] == out["single_calls"] + out["map_calls"] + out["reduce_calls"]
    assert out["truncated_texts"] == 0
    # no source dropped — every passage is in some prompt
    joined = "\n".join(llm.prompts)
    for text in texts.values():
        assert text in joined
    # and no prompt exceeded the budget
    assert max(len(p) for p in llm.prompts) <= 3000


def test_a_passage_larger_than_the_whole_budget_is_truncated_and_counted():
    """A single passage that cannot fit any batch is truncated — and the truncation is REPORTED.

    Silently dropping the tail of a passage is the V6 failure in miniature. Removing the
    `truncated += 1` fails this test.
    """
    names = ["a0", "a1"]
    edges = [("a0", "a1", 1.0)]
    g = read_concept_graph(FakeSession(names, edges), "doc1")
    h = build_hierarchy(g, resolutions=(0.5, 1.0, 2.0))
    huge = "y" * 5000
    llm = FakeLLM()
    out = summarize_communities(h, {"a0": ["c0"], "a1": []}, _provider({"c0": huge}), llm=llm,
                                dry_run=False, max_prompt_chars=2000)
    assert out["truncated_texts"] == 1
    assert max(len(p) for p in llm.prompts) <= 2000


def test_a_real_run_records_prompt_chars_per_level_too():
    """The cost ledger must record the prompt characters on a REAL run, not only on a dry one.

    Measured 2026-10-22: after the batching rewrite the live §G2 build wrote
    `prompt_chars_by_level: {}` — the ledger recorded the calls but not what they cost. Reverting
    the `prompt_chars_by_level[...] + counters["prompt_chars"] - before_chars` accumulation fails
    this test.
    """
    h, concept_chunks, texts = _long_text_hierarchy()
    out = summarize_communities(h, concept_chunks, _provider(texts), llm=FakeLLM(), dry_run=False)
    assert out["total_calls"] > 0
    assert sum(out["prompt_chars_by_level"].values()) == out["prompt_chars_total"] > 0
    assert set(out["prompt_chars_by_level"]) == set(out["calls_by_level"])


def test_dry_run_plans_the_calls_a_real_run_performs():
    """The pre-flight report must count the prompts the run will actually issue at the leaf level (V4).

    ⚠️ The quantity is leaf PROMPTS — `single_calls + map_calls` at the leaf level, excluding the leaf
    reduce calls — and `leaf_prompt_calls` is its real-run counterpart. Two wrong comparisons were
    made here before it: against `map_calls` (which excludes single-batch communities, so it reads 0
    on the live corpus while the plan reads 218) and against `calls_by_level[0]` (which *includes*
    the leaf reduce calls). Both passed or failed depending on the fixture, which is the defect. The
    independent reviewer found the first of the two, 2026-10-22.
    """
    h, concept_chunks, texts = _long_text_hierarchy()
    provider = _provider(texts)
    dry = summarize_communities(h, concept_chunks, provider, llm=FakeLLM(),
                                dry_run=True, max_prompt_chars=3000)
    real = summarize_communities(h, concept_chunks, provider, llm=FakeLLM(),
                                 dry_run=False, max_prompt_chars=3000)

    assert dry["total_calls"] == 0                      # still no spend on a dry run
    assert dry["planned_leaf_batched_communities"] == real["batched_communities"]
    # the exact quantity: leaf PROMPTS (single + map), excluding the leaf reduce calls
    assert dry["planned_leaf_prompts"] == real["leaf_prompt_calls"]
    assert dry["planned_leaf_prompts"] > len(h.levels[0].communities) // 2


def test_planned_leaf_prompts_counts_single_call_communities_too():
    """The plan is the leaf level's PROMPT count, so it must include communities that do NOT batch.

    This is the case the old name (`planned_leaf_map_calls`) and the old test both missed: with a
    budget large enough for every community to fit in one call, the plan must equal the number of
    leaves that have source material, while a real run records **zero** map calls.
    """
    h, concept_chunks, texts = _long_text_hierarchy()
    provider = _provider(texts)
    dry = summarize_communities(h, concept_chunks, provider, llm=FakeLLM(),
                                dry_run=True, max_prompt_chars=400_000)
    real = summarize_communities(h, concept_chunks, provider, llm=FakeLLM(),
                                 dry_run=False, max_prompt_chars=400_000)

    assert dry["planned_leaf_batched_communities"] == 0     # nothing batches at this budget
    assert real["map_calls"] == 0 and real["reduce_calls"] == 0
    assert dry["planned_leaf_prompts"] == real["leaf_prompt_calls"] == len(h.levels[0].communities)
    # ...and the OLD comparison would have failed here, which is why it was wrong
    assert dry["planned_leaf_prompts"] != real["map_calls"]


def test_reduce_terminates_when_summaries_do_not_shrink():
    """The `len(merged) >= len(parts): break` guard is load-bearing — this is the case it exists for.

    If a reduce returns a summary at least as long as the budget, `_batch_texts` puts one per group
    (a full-room text cannot share a batch), so the merge does NOT shrink the list. Without the guard
    `parts = merged` would leave the loop at the same length with the same content, forever. The
    independent reviewer read this as a reachable infinite loop; it is reachable only with the guard
    removed, which is what this test pins. Removing the guard makes this test hang.
    """
    h, concept_chunks, texts = _long_text_hierarchy()

    def llm(_prompt):
        return "z" * 3000          # >= the budget, so every merge yields one full-room group

    out = summarize_communities(h, concept_chunks, _provider(texts), llm=llm,
                                dry_run=False, max_prompt_chars=3000)

    assert out["map_calls"] > 0 and out["reduce_calls"] > 0
    assert out["empty_returns"] == 0
    assert out["total_calls"] == out["single_calls"] + out["map_calls"] + out["reduce_calls"]


def test_reduce_that_always_fails_terminates_and_reports_empty():
    """Disproves the reviewer's 'blocker: the reduce loop can cycle forever'.

    When every reduce call returns "", `merged` is empty, `parts` becomes empty, and `len(parts) > 1`
    is False — so the loop exits and the community's summary is "" with every failure counted. If
    this ever hung, the test would time out.
    """
    h, concept_chunks, texts = _long_text_hierarchy()

    class ReduceAlwaysFails:
        """Non-empty for the MAP prompts (so batching starts), empty for every REDUCE prompt."""

        def __init__(self):
            self.prompts = []

        def __call__(self, prompt):
            self.prompts.append(prompt)
            return "" if prompt.startswith(PARENT_PROMPT.split("{body}")[0]) else "a batch summary"

    llm = ReduceAlwaysFails()
    out = summarize_communities(h, concept_chunks, _provider(texts), llm=llm,
                                dry_run=False, max_prompt_chars=3000)

    assert out["batched_communities"] > 0 and out["map_calls"] > 0 and out["reduce_calls"] > 0
    assert out["empty_returns"] == out["reduce_calls"]     # every reduce call failed and is counted
    assert out["total_calls"] == out["single_calls"] + out["map_calls"] + out["reduce_calls"]
    # every community that batched ended with NO summary, and nothing raised or hung
    assert sum(1 for v in out["summaries"].values() if not (v or "").strip()) >= out["batched_communities"]


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
