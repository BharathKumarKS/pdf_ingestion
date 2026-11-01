"""Lane plan S3 — the RAPTOR lane on the EVAL path, and the fused-arm selector.

Before S3 the eval path could not reach any lane as a first-class RRF participant: `run_retrieval`
always called `search_with_das` (DA appended after the fusion), appended the graph lane itself after
dedup/MMR with a fabricated `score`, and **never called `search_raptor` at all** — the lane existed in
`store` and on the Streamlit page, but not on the measurement path. `run_retrieval(lanes=...)` is the
selector the lane-inclusion arms use; `lanes=None` must remain BYTE-FOR-BYTE today's wiring.

Four properties are pinned, each of which CAN fail:

  1. `lanes=None` is today's wiring — `search_with_das` runs, `search_fused` does NOT, and the graph
     lane is still appended post-MMR for multihop;
  2. the RAPTOR lane FIRES for an overview query and is NOT called for factual/multihop (the gate);
  3. a RAPTOR hit reaches the POOL and carries an `rrf_score` — i.e. it went through `_rrf_merge`
     rather than being appended;
  4. a fused arm's graph hits come through the FUSION (rrf_score present, no fabricated `score=1.0`),
     which is what makes F2 a placement change rather than a copy of F0.

Mutation proof: `logs/p1/step10/lane_inclusion_eval_mutation_log.txt`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from src.core.config import Settings

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_rag.py"


@pytest.fixture(scope="module")
def ev():
    spec = importlib.util.spec_from_file_location("evaluate_rag_s3_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def cfg():
    return Settings(hyde_enabled=False, reranker_enabled=True, reranker_fetch_k=100,
                    reranker_top_k=20, qdrant_in_memory=True, da_enabled=True)


class _Emb:
    def embed_query(self, _text):
        return [0.0] * 768


class _Reranker:
    fallbacks = 0
    last_fallback = None

    def rerank(self, _q, chunks, top_k):
        return chunks[:top_k]


def _hits(prefix: str, n: int, start_page: int = 100, page: bool = True):
    return [{"chunk_id": f"{prefix}{i}", "text": f"{prefix} {i}", "score": 1.0 / (i + 1),
             **({"page_number": start_page + i} if page else {})} for i in range(n)]


def _graph_hits(prefix: str, n: int, start_page: int = 300):
    """The REAL `graph_search` shape: `page_num` / `text_preview` / `chunk_id` and **no `score`**.

    That absence is load-bearing: the append path's `gh.setdefault("score", 1.0)` fabricates one
    only when the key is missing, so a fixture that supplies a score cannot show the fabrication.
    """
    return [{"chunk_id": f"{prefix}{i}", "text_preview": f"{prefix} {i}", "page_num": start_page + i}
            for i in range(n)]


def _raptor_hits(n: int = 2):
    """The REAL `search_raptor` shape — and the shape is the point.

    A RAPTOR summary is a **payload-only** dict: `raptor_node_id`, `raptor_level`, `text`, and
    **no `chunk_id`**. `_rrf_merge` keys a candidate on `chunk_id` falling back to
    `qdrant_point_id`, so a fixture that hands the fusion a `chunk_id` (the first version of these
    tests did) cannot see the defect that made every RAPTOR candidate vanish inside `search_fused`.
    """
    return [{"score": 0.7 - i / 10, "qdrant_point_id": f"rpid{i}", "raptor_node_id": f"rn{i}",
             "raptor_level": 1, "text": f"summary {i}"} for i in range(n)]


class _Recorder:
    """Records how each lane was reached, so a test can assert on the CALL and not only on output."""

    def __init__(self):
        self.calls: list[str] = []
        self.fused_lanes: tuple | None = None
        self.fused_kwargs: dict = {}


def _store(settings, monkeypatch, rec, *, vec, da, graph, raptor=None):
    """A REAL DocumentStore with its lanes stubbed — so `search_fused` is the product's own code."""
    from src.pdf_ingestion.store import DocumentStore

    s = DocumentStore(settings)
    orig_das, orig_fused = s.search_with_das, s.search_fused

    def _das(*a, **k):
        rec.calls.append("search_with_das")
        return list(vec)

    def _fused(*a, **k):
        rec.calls.append("search_fused")
        rec.fused_lanes = k.get("lanes")
        rec.fused_kwargs = dict(k)
        return orig_fused(*a, **k)

    monkeypatch.setattr(s, "search_with_das", _das)
    monkeypatch.setattr(s, "search_fused", _fused)
    monkeypatch.setattr(s, "search", lambda *a, **k: list(vec))
    monkeypatch.setattr(s, "search_da", lambda *a, **k: list(da))
    monkeypatch.setattr(s, "_resolve_da_parents", lambda hits: list(hits))
    if raptor is not None:
        def _raptor(*a, **k):
            rec.calls.append("search_raptor")
            return list(raptor)
        monkeypatch.setattr(s, "search_raptor", _raptor)

    class _FakeGraph:
        def graph_search(self, **k):
            rec.calls.append("graph_search")
            return list(graph)

    import src.pdf_ingestion.graph_builder as gb
    monkeypatch.setattr(gb, "get_graph_builder", lambda cfg: _FakeGraph())
    return s


# ── 1. lanes=None IS today's wiring ──────────────────────────────────────────────────────────

def test_default_lanes_none_uses_todays_wiring(ev, cfg, monkeypatch):
    rec = _Recorder()
    s = _store(cfg, monkeypatch, rec, vec=_hits("v", 3), da=_hits("d", 2, 200),
               graph=_graph_hits("g", 2), raptor=_raptor_hits(2))

    out = ev.run_retrieval("q", s, _Emb(), _Reranker(), cfg, "global", 0.0,
                           query_type="multihop")

    assert rec.calls.count("search_with_das") == 1, "the control must call the shipped entry point"
    assert "search_fused" not in rec.calls, "lanes=None must NOT route through the fusion"
    assert "search_raptor" not in rec.calls, "RAPTOR is not on today's eval path"
    # the graph lane is still appended by the CALLER, with its fabricated score — that IS the control
    appended = [h for h in out["hits"] if str(h.get("chunk_id", "")).startswith("g")]
    assert appended, "the multihop graph append must still happen under lanes=None"
    assert all(h.get("score") == 1.0 for h in appended), (
        "the control's score-less graph hits must get the FABRICATED score=1.0 "
        "(`evaluate_rag.py:245`) — this is exactly what F2 removes")
    assert all("rrf_score" not in h for h in appended), \
        "an appended graph hit must NOT carry an rrf_score — it never went through the fusion"
    assert all(h.get("page_number") == 300 + i for i, h in enumerate(appended)), \
        "the append path must still map graph `page_num` -> `page_number`"


# ── 2. the RAPTOR gate ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("qtype,called", [("overview", True), ("factual", False), ("multihop", False)])
def test_raptor_lane_fires_only_for_overview(ev, cfg, monkeypatch, qtype, called):
    rec = _Recorder()
    s = _store(cfg, monkeypatch, rec, vec=_hits("v", 3), da=_hits("d", 2, 200),
               graph=_graph_hits("g", 2), raptor=_raptor_hits(2))

    out = ev.run_retrieval("q", s, _Emb(), _Reranker(), cfg, "global", 0.0,
                           query_type=qtype, lanes=("raptor",))

    assert ("search_raptor" in rec.calls) is called, (
        f"search_raptor called={('search_raptor' in rec.calls)} for query_type={qtype!r}")
    assert ("rn0" in [h.get("raptor_node_id") for h in out["hits"]]) is called, (
        "the RAPTOR candidate must reach the pool for an overview query — and must NOT be dropped "
        "by the fusion for lacking a `chunk_id`")
    # and the lane set actually handed to the fusion carries the same gate
    assert rec.fused_lanes is not None
    assert (("raptor" in rec.fused_lanes) is called), rec.fused_lanes


def test_raptor_gate_is_applied_to_the_lane_set_not_only_to_the_call(ev, cfg, monkeypatch):
    """A factual query asking for (da, raptor) must hand the fusion (da,) — the gate is not cosmetic."""
    rec = _Recorder()
    s = _store(cfg, monkeypatch, rec, vec=_hits("v", 3), da=_hits("d", 2, 200),
               graph=_graph_hits("g", 2), raptor=_raptor_hits(2))

    ev.run_retrieval("q", s, _Emb(), _Reranker(), cfg, "global", 0.0,
                     query_type="factual", lanes=("da", "raptor"))

    assert rec.fused_lanes == ("da",), rec.fused_lanes


# ── 3. the RAPTOR hit reaches the POOL, through the fusion ───────────────────────────────────

def test_raptor_hit_reaches_the_pool_through_the_fusion(ev, cfg, monkeypatch):
    rec = _Recorder()
    s = _store(cfg, monkeypatch, rec, vec=_hits("v", 4), da=_hits("d", 2, 200),
               graph=_graph_hits("g", 2), raptor=_raptor_hits(2))

    out = ev.run_retrieval("q", s, _Emb(), _Reranker(), cfg, "global", 0.0,
                           query_type="overview", lanes=("raptor",))

    ids = [h.get("qdrant_point_id") for h in out["hits"]]
    assert "rpid0" in ids, (
        f"the RAPTOR candidate never reached the pool: {ids} — `_rrf_merge` keys on "
        f"`chunk_id`/`qdrant_point_id`, and a payload-only RAPTOR dict has neither")
    r0 = next(h for h in out["hits"] if h.get("qdrant_point_id") == "rpid0")
    assert "rrf_score" in r0 and r0["rrf_score"] > 0, (
        "a RAPTOR candidate without an rrf_score was APPENDED, not fused — the lane is not a "
        "first-class participant")
    # page-less, and that is the structural fact the pre-registration must state (§S3 docstring)
    assert r0.get("page_number") is None
    assert r0.get("raptor_node_id") == "rn0", "the payload must survive the fusion intact"


def test_the_real_search_raptor_returns_a_key_the_fusion_can_use(settings, monkeypatch):
    """⚠️ The regression the LIVE probe found, pinned against the REAL `search_raptor`.

    Every test above STUBS `search_raptor`, so none of them can see the shape the real lane
    returns — and the real lane returned `{"score": …, **payload}`, which carries **no `chunk_id`
    and no `qdrant_point_id`**. `_rrf_merge` keys on exactly those, so it dropped every RAPTOR
    candidate: the lane was wired and contributed NOTHING, and an arm that "adds the RAPTOR lane"
    was a copy of its control. Measured live 2026-10-30 (`lane_inclusion_s3_live_probe.json`).
    """
    from src.pdf_ingestion.store import DocumentStore

    class _Pt:
        id = "raptor-point-uuid"
        score = 0.9
        payload = {"raptor_node_id": "rn0", "raptor_level": 1, "text": "a summary"}

    class _Resp:
        points = [_Pt()]

    s = DocumentStore(settings)
    monkeypatch.setattr(s._qdrant, "query_points", lambda **k: _Resp())

    out = s.search_raptor(np.ones(768, dtype=np.float32), tenant_id="global")

    assert out, "search_raptor returned nothing for a well-formed response"
    assert out[0].get("qdrant_point_id") == "raptor-point-uuid", (
        "the RAPTOR lane's candidate must carry the point id, or `_rrf_merge` drops it")
    assert "chunk_id" not in out[0], "a RAPTOR summary has no chunk_id — that is why the key matters"

    merged = DocumentStore._rrf_merge(
        out, [{"chunk_id": "v0", "page_number": 1, "text": "x", "score": 0.5}], rrf_k=1)
    assert any(h.get("raptor_node_id") == "rn0" for h in merged), (
        "the RAPTOR candidate vanished inside the fusion — the lane contributes nothing")


# ── 4. a fused arm does not append the graph lane post-MMR ───────────────────────────────────

def test_fused_graph_arm_goes_through_the_fusion_not_the_append(ev, cfg, monkeypatch):
    rec = _Recorder()
    s = _store(cfg, monkeypatch, rec, vec=_hits("v", 3), da=_hits("d", 2, 200),
               graph=_graph_hits("g", 2), raptor=_raptor_hits(2))

    out = ev.run_retrieval("q", s, _Emb(), _Reranker(), cfg, "global", 0.0,
                           query_type="multihop", lanes=("graph",))

    assert "search_with_das" not in rec.calls
    g = [h for h in out["hits"] if str(h.get("chunk_id", "")).startswith("g")]
    assert g, "the graph lane's candidates vanished from the fused pool"
    assert all("rrf_score" in h for h in g), "the graph lane was appended, not fused"
    assert all(h.get("score") != 1.0 for h in g), (
        "the fabricated score=1.0 is still being set — the append path was not bypassed")


def test_fused_arm_passes_the_graph_lane_the_raw_query_vector(ev, cfg, monkeypatch):
    """F2 must isolate PLACEMENT: the graph lane keeps the query vector the append path gave it.

    ⚠️ HyDE is ON here on purpose. With HyDE off, `search_vec IS q_vec` (the same object), so this
    test cannot discriminate a `graph_vector=q_vec` from a `graph_vector=search_vec` — the first
    version of this test passed under exactly that mutation. Two DIFFERENT vectors are the premise.
    """
    rec = _Recorder()
    s = _store(cfg, monkeypatch, rec, vec=_hits("v", 3), da=_hits("d", 2, 200),
               graph=_graph_hits("g", 2), raptor=_raptor_hits(2))

    class _VecEmb:
        def embed_query(self, text):
            return [7.0] * 768 if text == "q" else [9.0] * 768

    import src.core.llm as llm_mod
    monkeypatch.setattr(llm_mod, "call_llm", lambda **k: "a hypothetical passage")

    cfg_h = cfg.model_copy(update={"hyde_enabled": True})
    # ⚠️ an OVERVIEW query, not multihop: HyDE is skipped for multihop
    # (`evaluate_rag.py:190`), so `search_vec` would stay `q_vec` and the check could not discriminate.
    ev.run_retrieval("q", s, _VecEmb(), _Reranker(), cfg_h, "global", 0.0,
                     query_type="overview", lanes=("graph",))

    gv = rec.fused_kwargs.get("graph_vector")
    assert gv is not None, "the graph lane must be given an explicit vector, not the fusion's default"
    assert list(np.asarray(gv)) == [7.0] * 768, (
        "the graph lane's vector must be the RAW query vector (evaluate_rag:231), so F2 isolates "
        "placement rather than the vector")
    # the premise of the check above: the fusion's own vector is a DIFFERENT vector here
    assert rec.fused_kwargs["raptor_vector"] is not None
    assert list(np.asarray(rec.fused_kwargs["raptor_vector"])) == [9.0] * 768
