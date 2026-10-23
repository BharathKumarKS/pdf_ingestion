"""§I53 — the §G2 community-summarisation checkpoint and its resume semantics, offline.

The load-bearing claims, each with the guard that carries it:

* a completed community is reused **without a call** (`checkpoint.lookup` → `summarize_communities`);
* a community whose calls returned **empty is NOT done** — reverting `ok=bool(summary.strip())` to a
  blanket `ok=True` makes `test_a_community_whose_calls_returned_empty_is_not_resumed` fail;
* an entry is reused only when its **input digest** matches — reverting the digest comparison in
  `lookup` makes `test_a_changed_passage_re_summarises_the_child_and_its_parent` fail;
* the run key covers the run's identity — reverting the model/seed check in `_load` makes
  `test_a_different_model_does_not_resume_the_other_runs_checkpoint` fail;
* a torn final line costs one community, never the file.

No model, no network, no Qdrant.
"""
from __future__ import annotations

import json

from src.pdf_ingestion.community_summaries import (
    build_hierarchy,
    read_concept_graph,
    summarize_communities,
)
from src.pdf_ingestion.summary_checkpoint import (
    SummaryCheckpoint,
    input_digest,
    prompt_digest,
    run_key,
)

DOC = "7ba61432-c5e0-416d-aecf-25a232523481"
PROMPTS = {"system": prompt_digest("s"), "leaf": prompt_digest("l"), "parent": prompt_digest("p")}


# ── the fakes the existing §G2 tests use (kept local so this file stands alone) ────────────────

class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return self._rows


class FakeSession:
    def __init__(self, names, edges=(), concept_chunks=None):
        self.names = names
        self.edges = list(edges)
        self.concept_chunks = concept_chunks or {}

    def run(self, cypher, **params):
        if "RETURN DISTINCT k.name AS name" in cypher:
            return FakeResult([{"name": n} for n in self.names])
        if "RETURN a.name AS a" in cypher:
            return FakeResult([{"a": a, "b": b, "w": w} for a, b, w in self.edges])
        if "collect(DISTINCT c.id) AS chunks" in cypher:
            return FakeResult([{"name": n, "chunks": self.concept_chunks.get(n, [])}
                               for n in self.names])
        return FakeResult([])


class FakeLLM:
    def __init__(self, prefix="summary"):
        self.prompts: list[str] = []
        self.prefix = prefix

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return f"{self.prefix}[{len(prompt)}]"


def _two_cliques():
    a = [f"a{i}" for i in range(6)]
    b = [f"b{i}" for i in range(6)]
    edges = []
    for group in (a, b):
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                edges.append((group[i], group[j], 1.0))
    edges.append(("a0", "b0", 1.0))
    return a + b, edges


def _fixture(passage="passage text"):
    names, edges = _two_cliques()
    concept_chunks = {n: [f"chunk-{n}"] for n in names}
    g = read_concept_graph(FakeSession(names, edges), DOC)
    h = build_hierarchy(g, resolutions=(0.5, 1.0, 2.0))
    texts = {f"chunk-{n}": passage for n in names}
    provider = lambda ids: [texts[i] for i in ids if i in texts]      # noqa: E731
    return h, concept_chunks, provider


def _open(tmp_path, **over):
    kw = dict(document_id=DOC, model="openai/gpt-oss-20b", seed=20261020,
              resolutions=(0.5, 1.0, 2.0), max_prompt_chars=400_000, prompt_digests=PROMPTS)
    kw.update(over)
    return SummaryCheckpoint.open(directory=tmp_path, **kw)


# ── the run key ───────────────────────────────────────────────────────────────────────────────

def test_run_key_covers_the_run_identity():
    """The key is the identity of the RUN. Every input that changes what a summary means must move it.

    Measured context (§I52/§I50 Finding 4): the summariser is `cfg.openai_model`, a DIFFERENT model
    from the graph build's extractor, and the Leiden seed decides which communities exist at all.
    """
    base = dict(document_id=DOC, model="m", seed=1, resolutions=(0.5, 1.0, 2.0),
                max_prompt_chars=100, prompt_digests={"leaf": "abc"})
    k = run_key(**base)
    assert k == run_key(**base)                                    # deterministic
    for field, value in (("document_id", "other-doc"), ("model", "m2"), ("seed", 2),
                         ("resolutions", (0.5, 1.0)), ("max_prompt_chars", 200),
                         ("prompt_digests", {"leaf": "xyz"})):
        changed = dict(base)
        changed[field] = value
        assert run_key(**changed) != k, f"{field} does not move the run key"


def test_input_digest_is_order_sensitive_and_content_sensitive():
    assert input_digest(["a", "b"]) != input_digest(["b", "a"])     # order is part of the input
    assert input_digest(["a", "b"]) != input_digest(["a", "b", "c"])
    assert input_digest(["a", "b"]) == input_digest(["a", "b"])
    # a separator is written between parts, so ("ab",) and ("a","b") cannot collide
    assert input_digest(["ab"]) != input_digest(["a", "b"])


# ── lookup / record ───────────────────────────────────────────────────────────────────────────

def test_lookup_hits_only_on_a_matching_digest(tmp_path):
    cp = _open(tmp_path)
    cp.record(0, 3, input_digest(["passage"]), "a summary", ok=True)
    assert cp.lookup(0, 3, input_digest(["passage"])) == "a summary"
    assert cp.resumed_communities == 1
    # a different input at the same (level, community) is NOT the recorded summary
    assert cp.lookup(0, 3, input_digest(["a different passage"])) is None
    assert cp.stale_communities == 1
    # and an unknown community is a miss, not an error
    assert cp.lookup(1, 99, input_digest(["x"])) is None


def test_a_failed_entry_is_not_a_hit(tmp_path):
    """A community whose calls returned empty is a FAILURE, and must be re-attempted (§I25)."""
    cp = _open(tmp_path)
    d = input_digest(["passage"])
    cp.record(0, 1, d, "", ok=False)
    assert cp.lookup(0, 1, d) is None
    assert cp.retried_communities == 1


def test_a_skipped_community_can_be_reused(tmp_path):
    """No source material is not a failure: it makes no call and its empty summary is legitimately done."""
    cp = _open(tmp_path)
    d = input_digest([])
    cp.record(0, 7, d, "", ok=True)
    assert cp.lookup(0, 7, d) == ""


# ── persistence, keys, crash safety ───────────────────────────────────────────────────────────

def test_a_reopened_checkpoint_resumes_what_it_recorded(tmp_path):
    first = _open(tmp_path)
    first.record(0, 1, input_digest(["p1"]), "s1", ok=True)
    first.record(1, 2, input_digest(["s1"]), "s2", ok=True)
    first.close()

    second = _open(tmp_path)
    assert len(second.entries) == 2
    assert second.lookup(0, 1, input_digest(["p1"])) == "s1"
    assert second.lookup(1, 2, input_digest(["s1"])) == "s2"


def test_a_different_model_does_not_resume_the_other_runs_checkpoint(tmp_path):
    """The checkpoint key includes the model — a model swap must not inherit the other model's tree.

    Reverting the `header.get("model") != self.model` check in `_load` fails this test.
    """
    a = _open(tmp_path, model="openai/gpt-oss-20b")
    a.record(0, 1, input_digest(["p"]), "s", ok=True)
    a.close()

    b = _open(tmp_path, model="Qwen/Qwen3-VL-8B-Instruct")
    assert b.path != a.path                       # a different run key, so a different file
    assert b.entries == {}


def test_a_header_that_does_not_match_is_ignored(tmp_path):
    """The header is the identity check (§I19a) — a file whose header disagrees is not resumed."""
    a = _open(tmp_path)
    a.record(0, 1, input_digest(["p"]), "s", ok=True)
    a.close()

    # Corrupt the header in place, keeping the file name (so only the header can catch it).
    lines = a.path.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["model"] = "some/other-model"
    a.path.write_text("\n".join([json.dumps(header)] + lines[1:]) + "\n", encoding="utf-8")

    b = _open(tmp_path)
    assert b.path == a.path
    assert b.entries == {}


def test_a_torn_final_line_costs_one_community_not_the_file(tmp_path):
    """Append-only JSONL + truncate-on-load: a crash may tear the last line, never the file."""
    cp = _open(tmp_path)
    for cid in range(4):
        cp.record(0, cid, input_digest([f"p{cid}"]), f"s{cid}", ok=True)
    cp.close()
    with cp.path.open("a", encoding="utf-8") as fh:
        fh.write('{"kind":"community","level":0,"community":4,"inpu')   # torn record

    reopened = _open(tmp_path)
    assert sorted(reopened.entries) == [(0, 0), (0, 1), (0, 2), (0, 3)]
    assert reopened.lookup(0, 0, input_digest(["p0"])) == "s0"
    # the file was rewound, so the next append is not preceded by a fragment
    reopened.record(0, 9, input_digest(["p9"]), "s9", ok=True)
    reopened.close()
    again = _open(tmp_path)
    assert sorted(again.entries) == [(0, 0), (0, 1), (0, 2), (0, 3), (0, 9)]


def test_fresh_discards_the_previous_checkpoint(tmp_path):
    cp = _open(tmp_path)
    cp.record(0, 1, input_digest(["p"]), "s", ok=True)
    cp.close()

    fresh = _open(tmp_path, fresh=True)
    assert fresh.entries == {}


def test_last_record_wins_for_a_re_attempted_community(tmp_path):
    """A community recorded failed and then re-attempted successfully must end up DONE."""
    cp = _open(tmp_path)
    d = input_digest(["p"])
    cp.record(0, 1, d, "", ok=False)
    cp.record(0, 1, d, "now it worked", ok=True)
    cp.close()
    assert _open(tmp_path).lookup(0, 1, d) == "now it worked"


# ── end to end: resume through summarize_communities ──────────────────────────────────────────

def test_resume_makes_no_calls_and_reproduces_the_tree(tmp_path):
    h, concept_chunks, provider = _fixture()
    cp = _open(tmp_path)
    first_llm = FakeLLM("first")
    first = summarize_communities(h, concept_chunks, provider, llm=first_llm,
                                  checkpoint=cp, dry_run=False)
    assert first["total_calls"] == len(first_llm.prompts) > 0
    assert first["resumed_communities"] == 0

    second_llm = FakeLLM("second")
    second = summarize_communities(h, concept_chunks, provider, llm=second_llm,
                                   checkpoint=cp, dry_run=False)

    assert second_llm.prompts == []                       # nothing re-asked
    assert second["total_calls"] == 0
    assert second["resumed_communities"] == len(first["summaries"])
    assert second["summaries"] == first["summaries"]      # byte-identical tree
    assert all(v.startswith("first") for v in second["summaries"].values())


def test_a_community_whose_calls_returned_empty_is_re_attempted_on_resume(tmp_path):
    """Reverting `ok=bool(summary.strip())` to a blanket ok=True fails this test.

    The whole point of the checkpoint is that a run aborted during an endpoint outage does not
    resume having "already completed" the communities whose calls returned nothing (§I25).
    """
    h, concept_chunks, provider = _fixture()
    cp = _open(tmp_path)
    failed = summarize_communities(h, concept_chunks, provider, llm=lambda p: "",
                                   checkpoint=cp, dry_run=False)
    assert failed["empty_returns"] == failed["total_calls"] > 0
    assert cp.retried_communities == 0                    # nothing was resumed: all failed

    healthy_llm = FakeLLM("recovered")
    recovered = summarize_communities(h, concept_chunks, provider, llm=healthy_llm,
                                      checkpoint=cp, dry_run=False)
    assert recovered["total_calls"] == len(healthy_llm.prompts) > 0   # re-attempted, not skipped
    assert recovered["resumed_communities"] == 0
    assert all(v.startswith("recovered") for v in recovered["summaries"].values())


def test_a_changed_passage_re_summarises_the_child_and_its_parent(tmp_path):
    """The input digest is what makes a resume correct: a changed leaf must not keep a stale parent.

    Reverting the digest comparison in `lookup` (so any entry at (level, cid) is a hit) fails this:
    the parent would be reused although its child's summary changed underneath it.
    """
    h, concept_chunks, _ = _fixture()
    cp = _open(tmp_path)
    texts = {f"chunk-{n}": "original passage" for n in [f"{g}{i}" for g in "ab" for i in range(6)]}
    first = summarize_communities(h, concept_chunks, lambda ids: [texts[i] for i in ids if i in texts],
                                  llm=FakeLLM("v1"), checkpoint=cp, dry_run=False)
    assert first["total_calls"] > 0

    # Same communities, but every leaf's passage has changed.
    texts2 = {k: "rewritten passage" for k in texts}
    second = summarize_communities(h, concept_chunks,
                                   lambda ids: [texts2[i] for i in ids if i in texts2],
                                   llm=FakeLLM("v2"), checkpoint=cp, dry_run=False)

    assert second["resumed_communities"] == 0
    assert second["stale_communities"] > 0
    assert second["total_calls"] > 0
    assert all(v.startswith("v2") for v in second["summaries"].values())
    # and nothing of the old tree survives
    assert not any(v.startswith("v1") for v in second["summaries"].values())


def test_a_dry_run_records_nothing_even_with_a_checkpoint(tmp_path):
    h, concept_chunks, provider = _fixture()
    cp = _open(tmp_path)
    llm = FakeLLM()
    out = summarize_communities(h, concept_chunks, provider, llm=llm,
                                checkpoint=cp, dry_run=True)
    assert llm.prompts == []
    assert out["total_calls"] == 0
    assert cp.entries == {}
    assert not cp.path.exists() or cp.path.read_text(encoding="utf-8") == ""
