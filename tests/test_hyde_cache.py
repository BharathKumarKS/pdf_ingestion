"""Tests for the HyDE cache (``src/pdf_ingestion/hyde_cache.py``).

The cache exists because HyDE's hypothetical was generated live per query, per arm, with no cache —
so two arms of an A/B embedded **different** text for the same query and the instrument moved the
number (§I68's class). What has to be true for it to be safe:

1. **A miss is LOUD and never generates.** A silent live LLM call mid-run reintroduces exactly the
   nondeterminism the cache removes.
2. **The header is validated on read, not just the filename.** A model, prompt or query-set change
   must make the file unusable rather than silently reuse text generated under the old one.
3. **An empty model return is a failure, not a cached value.** The §I25 shape: a total loss that
   reads as a success.
4. **A rebuild reuses what is already there.** Otherwise the "cache" costs a full LLM pass every
   run, which is the defect it was written to avoid.
5. **The prompt in this module cannot drift from the deployed call sites.** It is duplicated in
   ``scripts/evaluate_rag.py`` and ``scripts/funnel_boundary_recall.py`` today; the cache key is
   derived from it, so a fork would silently key the cache on a prompt nothing sends.

Offline throughout: ``call_llm`` is monkeypatched, and the cache dir is a ``tmp_path``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.pdf_ingestion import hyde_cache as hc

REPO = Path(__file__).resolve().parents[1]


# ── helpers ────────────────────────────────────────────────────────────────

class _Recorder:
    """Stands in for ``src.core.llm.call_llm``; records calls, returns a canned reply."""

    def __init__(self, reply: str = "Entropy counts the microscopic configurations of a system."):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def __call__(self, prompt: str, system: str = "", settings=None, **kw) -> str:
        self.calls.append((prompt, system))
        return self.reply


def _queries_file(tmp_path: Path, body: str | None = None, name: str = "queries.json") -> Path:
    p = tmp_path / name
    p.write_text(body or '[{"id": "gold-001", "query": "what is entropy", "query_type": "factual"}]',
                 encoding="utf-8")
    return p


def _queries() -> list[dict]:
    return [
        {"id": "gold-001", "query": "what is entropy", "query_type": "factual"},
        {"id": "ovw-001", "query": "give me an overview", "query_type": "overview"},
        {"id": "gold-002", "query": "trace this chain", "query_type": "multihop"},
        {"id": "gold-003", "query": "what does figure 3 show", "query_type": "visual"},
    ]


@pytest.fixture
def rec(monkeypatch):
    r = _Recorder()
    monkeypatch.setattr("src.core.llm.call_llm", r)
    return r


@pytest.fixture
def cfg():
    class _Cfg:
        openai_model = "openai/gpt-oss-20b"
    return _Cfg()


@pytest.fixture(autouse=True)
def _cache_dir_in_tmp(tmp_path, monkeypatch):
    """Keep every write inside the test's tmp_path, never the repo's data/ dir."""
    monkeypatch.setattr(hc, "CACHE_DIR", str(tmp_path / "hyde_cache"))


# ── the key ────────────────────────────────────────────────────────────────

def test_path_carries_queries_model_and_prompt_digests(tmp_path):
    qf = _queries_file(tmp_path)
    p = hc.cache_path(qf, "some/model", repo_root=tmp_path)
    assert hc.queries_digest(qf) in p.name
    assert "some_model" in p.name          # '/' replaced so it stays one filename
    assert hc.prompt_digest() in p.name


def test_path_changes_when_the_queries_file_changes(tmp_path):
    a = _queries_file(tmp_path, '[{"id": "gold-001", "query": "what is entropy"}]', "a.json")
    b = _queries_file(tmp_path, '[{"id": "gold-001", "query": "what is enthalpy"}]', "b.json")
    assert hc.cache_path(a, "m", tmp_path) != hc.cache_path(b, "m", tmp_path)


def test_path_changes_when_the_model_changes(tmp_path):
    qf = _queries_file(tmp_path)
    assert hc.cache_path(qf, "m/one", tmp_path) != hc.cache_path(qf, "m/two", tmp_path)


def test_prompt_digest_covers_the_system_message_too(tmp_path, monkeypatch):
    """A system-message change changes the text the model was given, so it must change the key."""
    before = hc.prompt_digest()
    monkeypatch.setattr(hc, "HYDE_SYSTEM", hc.HYDE_SYSTEM + " Be terse.")
    assert hc.prompt_digest() != before


# ── load: absent, and header mismatches ────────────────────────────────────

def test_load_without_a_file_is_loud_and_does_not_generate(tmp_path, cfg, rec):
    with pytest.raises(hc.HydeCacheError) as e:
        hc.load(_queries_file(tmp_path), cfg=cfg)
    assert "Refusing to call the LLM mid-run" in str(e.value)
    assert rec.calls == []


def test_load_refuses_a_header_that_disagrees(tmp_path, cfg, rec):
    qf = _queries_file(tmp_path)
    hc.build(qf, _queries(), cfg=cfg)
    path = hc.cache_path(qf, cfg.openai_model, tmp_path)

    import json
    payload = json.loads(path.read_text())
    for field, bad in (("model", "someone/else"),
                       ("prompt_digest", "deadbeefdeadbeef"),
                       ("queries_digest", "0000000000000000"),
                       ("schema_version", 99)):
        mutated = json.loads(json.dumps(payload))
        mutated["meta"][field] = bad
        path.write_text(json.dumps(mutated), encoding="utf-8")
        with pytest.raises(hc.HydeCacheError) as e:
            hc.load(qf, cfg=cfg)
        assert field in str(e.value), f"{field} mismatch was not caught"
    assert rec.calls, "the build should have made calls"


# ── get: a miss is loud, never a generation ────────────────────────────────

def test_get_raises_on_a_miss_and_never_calls_the_llm(tmp_path, cfg, rec):
    qf = _queries_file(tmp_path)
    hc.build(qf, _queries(), cfg=cfg)
    n_after_build = len(rec.calls)
    cache = hc.load(qf, cfg=cfg)
    assert cache.lookup("gold-999") is None
    with pytest.raises(hc.HydeCacheMiss) as e:
        cache.get("gold-999")
    assert "gold-999" in str(e.value)
    assert len(rec.calls) == n_after_build, "get() must not generate"


# ── build ──────────────────────────────────────────────────────────────────

def test_build_only_targets_factual_and_overview(tmp_path, cfg, rec):
    qf = _queries_file(tmp_path)
    cache = hc.build(qf, _queries(), cfg=cfg)
    assert sorted(cache.entries) == ["gold-001", "ovw-001"]
    assert len(rec.calls) == 2
    assert cache.meta["n_targets"] == 2 and cache.meta["n_generated"] == 2


def test_second_build_reuses_everything(tmp_path, cfg, rec):
    qf = _queries_file(tmp_path)
    hc.build(qf, _queries(), cfg=cfg)
    n = len(rec.calls)
    again = hc.build(qf, _queries(), cfg=cfg)
    assert len(rec.calls) == n, "a rebuild must not re-call the model"
    assert again.meta["n_reused"] == 2 and again.meta["n_generated"] == 0


def test_an_empty_return_is_a_failure_not_a_cached_value(tmp_path, cfg, monkeypatch):
    """§I25's shape: a 200 with empty content must not enter the cache as if it worked."""
    r = _Recorder(reply="   ")
    monkeypatch.setattr("src.core.llm.call_llm", r)
    qf = _queries_file(tmp_path)
    cache = hc.build(qf, _queries(), cfg=cfg)
    assert cache.entries == {}, "an empty reply was cached"
    assert cache.meta["n_failed"] == 2
    assert {f["id"] for f in cache.meta["failures"]} == {"gold-001", "ovw-001"}
    assert "empty model return" in cache.meta["failures"][0]["error"]
    # and a later load must still refuse the missing ids rather than hand back ""
    with pytest.raises(hc.HydeCacheMiss):
        hc.load(qf, cfg=cfg).get("gold-001")


def test_a_raised_call_is_counted_and_not_cached(tmp_path, cfg, monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("cluster down")
    monkeypatch.setattr("src.core.llm.call_llm", _boom)
    qf = _queries_file(tmp_path)
    cache = hc.build(qf, _queries(), cfg=cfg)
    assert cache.meta["n_failed"] == 2
    assert "RuntimeError" in cache.meta["failures"][0]["error"]


def test_write_is_atomic_and_leaves_no_tmp_file(tmp_path, cfg, rec):
    qf = _queries_file(tmp_path)
    cache = hc.build(qf, _queries(), cfg=cfg)
    assert cache.path.exists()
    assert not list(cache.path.parent.glob("*.tmp")), "a .tmp file survived the write"


def test_the_prompt_is_the_one_the_deployed_call_sites_send():
    """The cache key derives from this module's prompt; the deployed copies live in scripts/.

    If either place changes, the cache would key on text nothing sends. This is the §I28 sweep
    applied to a duplicated constant.
    """
    frags = [
        "Write 2-3 sentences of physics textbook content ",
        "that directly answers: ",
        "You are a physics textbook author. Write factual content only. ",
        "No preamble, no 'Here is...', just the content itself.",
    ]
    for rel in ("scripts/evaluate_rag.py", "scripts/funnel_boundary_recall.py"):
        src = (REPO / rel).read_text(encoding="utf-8")
        for frag in frags:
            assert frag in src, f"{rel} no longer contains {frag!r} — the prompt forked"


def test_prompt_for_renders_the_query(tmp_path):
    assert hc.prompt_for("what is entropy").endswith("that directly answers: what is entropy")
