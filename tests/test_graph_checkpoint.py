"""Tests for the Phase 3 concept-extraction checkpoint (§I23).

Local only: no Memgraph, no cluster, no LLM. The graph write path is replaced by fakes, and the
extractor by a stub, so what is under test is the checkpoint and the failure accounting — the two
things §I23 found missing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.config import Settings
from src.pdf_ingestion.chunker import TextChunk
from src.pdf_ingestion.graph_builder import GraphBuilder
from src.pdf_ingestion.graph_checkpoint import GraphCheckpoint, prompt_digest, run_key


# ── fixtures / helpers ────────────────────────────────────────────────────────

@pytest.fixture
def cp_settings(tmp_path):
    return Settings(
        use_stub_embedder=True,
        use_stub_llm=True,
        use_stub_colpali=True,
        use_stub_graph=True,
        qdrant_in_memory=True,
        sqlite_url=f"sqlite:///{tmp_path}/test_graph_cp.db",
        graph_checkpoint_dir=str(tmp_path / "graph_cache"),
        debug=False,
    )


def _chunks(n=5, doc="doc-graph"):
    return [
        TextChunk(
            chunk_id=f"chunk-{i}",
            document_id=doc,
            tenant_id="global",
            chunk_index=i,
            text=f"Physics text number {i} about force and energy.",
            char_start=i * 100,
            char_end=(i + 1) * 100,
            token_count=20,
            page_number=i + 1,
        )
        for i in range(n)
    ]


def _ok(concepts=("force",)):
    return {"concepts": [{"name": c} for c in concepts], "prerequisites": [],
            "ok": True, "error": None}


def _fail(msg="boom"):
    return {"concepts": [], "prerequisites": [], "ok": False, "error": msg}


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, *args, **kwargs):
        return None


class _FakeDriver:
    def session(self):
        return _FakeSession()


def _open(tmp_path, chunks, model="m1", pd="p1", fresh=False):
    return GraphCheckpoint.open(
        directory=tmp_path, document_id="doc-graph",
        chunk_ids=[c.chunk_id for c in chunks], model=model, prompt_digest_=pd, fresh=fresh,
    )


# ── run key ───────────────────────────────────────────────────────────────────

class TestRunKey:
    def test_stable_for_the_same_inputs(self):
        assert run_key("d", "m", "p") == run_key("d", "m", "p")

    def test_changes_with_each_component(self):
        base = run_key("d", "m", "p")
        assert run_key("d2", "m", "p") != base
        assert run_key("d", "m2", "p") != base
        assert run_key("d", "m", "p2") != base

    def test_prompt_digest_tracks_the_prompt_text(self):
        assert prompt_digest("extract concepts") != prompt_digest("extract concepts please")
        assert prompt_digest("x") == prompt_digest("x")


# ── checkpoint: record / reload ───────────────────────────────────────────────

class TestCheckpointRoundTrip:
    def test_fresh_checkpoint_is_empty(self, tmp_path):
        cp = _open(tmp_path, _chunks())
        assert cp.done == set()
        assert cp.extractions == {}

    def test_record_then_reload_returns_the_extractions(self, tmp_path):
        chunks = _chunks()
        cp = _open(tmp_path, chunks)
        cp.record(chunks[0].chunk_id, 0, _ok(("force", "energy")))
        cp.record(chunks[1].chunk_id, 1, _ok(("momentum",)))
        cp.close()

        again = _open(tmp_path, chunks)
        assert again.done == {chunks[0].chunk_id, chunks[1].chunk_id}
        assert again.resumed_chunks == 2
        assert [c["name"] for c in again.extractions[chunks[0].chunk_id]["concepts"]] == \
            ["force", "energy"]

    def test_a_failed_extraction_is_not_treated_as_done(self, tmp_path):
        """The whole point (§I23): 44 failures were reported as '0 failed'. A checkpoint that
        recorded them as complete would bake the loss in permanently."""
        chunks = _chunks()
        cp = _open(tmp_path, chunks)
        cp.record(chunks[0].chunk_id, 0, _ok())
        cp.record(chunks[1].chunk_id, 1, _fail())
        cp.close()

        again = _open(tmp_path, chunks)
        assert again.done == {chunks[0].chunk_id}
        assert again.retried_chunks == 1
        assert chunks[1].chunk_id not in again.extractions

    def test_entry_for_an_unknown_chunk_is_ignored(self, tmp_path):
        chunks = _chunks()
        cp = _open(tmp_path, chunks)
        cp.record("chunk-from-another-ingest", 99, _ok())
        cp.close()

        again = _open(tmp_path, chunks)
        assert again.done == set()
        assert again.ignored_chunks == 1

    def test_fresh_discards_an_existing_file(self, tmp_path):
        chunks = _chunks()
        cp = _open(tmp_path, chunks)
        cp.record(chunks[0].chunk_id, 0, _ok())
        cp.close()

        fresh = _open(tmp_path, chunks, fresh=True)
        assert fresh.done == set()


# ── checkpoint: identity ──────────────────────────────────────────────────────

class TestCheckpointIdentity:
    def test_a_different_model_is_not_resumed(self, tmp_path):
        chunks = _chunks()
        cp = _open(tmp_path, chunks, model="m1")
        cp.record(chunks[0].chunk_id, 0, _ok())
        cp.close()
        # Same path is derived from the key, so a model change names a different file entirely.
        assert _open(tmp_path, chunks, model="m2").done == set()

    def test_a_different_prompt_digest_is_not_resumed(self, tmp_path):
        chunks = _chunks()
        cp = _open(tmp_path, chunks, pd="p1")
        cp.record(chunks[0].chunk_id, 0, _ok())
        cp.close()
        assert _open(tmp_path, chunks, pd="p2").done == set()

    def test_a_header_that_disagrees_is_ignored(self, tmp_path):
        """A file whose NAME matches but whose header does not must not be resumed (§I19a)."""
        chunks = _chunks()
        cp = _open(tmp_path, chunks)
        cp.record(chunks[0].chunk_id, 0, _ok())
        cp.close()

        # Rewrite the header's document id, leaving the name alone.
        path = next(Path(tmp_path).glob("*.jsonl"))
        lines = path.read_text().splitlines()
        header = json.loads(lines[0])
        header["document_id"] = "someone-elses-doc"
        lines[0] = json.dumps(header)
        path.write_text("\n".join(lines) + "\n")

        assert _open(tmp_path, chunks).done == set()


# ── checkpoint: crash safety ──────────────────────────────────────────────────

class TestCheckpointTornWrite:
    def test_a_torn_final_line_costs_one_chunk_not_the_file(self, tmp_path):
        chunks = _chunks()
        cp = _open(tmp_path, chunks)
        cp.record(chunks[0].chunk_id, 0, _ok())
        cp.record(chunks[1].chunk_id, 1, _ok())
        cp.close()

        path = next(Path(tmp_path).glob("*.jsonl"))
        with path.open("a") as fh:
            fh.write('{"kind":"chunk","chunk_id":"chunk-9","conce')   # torn

        again = _open(tmp_path, chunks)
        assert again.done == {chunks[0].chunk_id, chunks[1].chunk_id}
        # ...and the file was rewound so the next append is not preceded by a fragment.
        assert '"chunk-9"' not in path.read_text()


# ── checkpoint: reporting cadence ─────────────────────────────────────────────

class TestCheckpointDue:
    def test_due_on_chunk_count(self, tmp_path):
        cp = _open(tmp_path, _chunks())
        cp.record("chunk-0", 0, _ok())
        assert cp.due(every=1, every_seconds=3600) is True

    def test_due_on_wall_clock_even_when_chunks_are_slow(self, tmp_path):
        """Chunk cost is not uniform — ~10 s healthy vs ~80 s under contention (§I23) — so a
        pure chunk-count interval can be an hour of silence."""
        cp = _open(tmp_path, _chunks())
        cp.record("chunk-0", 0, _ok())
        assert cp.due(every=1000, every_seconds=0.0) is True


# ── extraction result: ok vs empty ────────────────────────────────────────────

class TestExtractConcepts:
    """`ok=False` must mean 'the call failed', never 'this chunk has no concepts'."""

    def _builder(self, cp_settings):
        return GraphBuilder(cp_settings)

    def _patch_llm(self, monkeypatch, behaviour):
        import src.core.llm as llm_mod
        monkeypatch.setattr(llm_mod, "call_llm", behaviour)

    def test_valid_json_with_no_concepts_is_ok(self, cp_settings, monkeypatch):
        self._patch_llm(monkeypatch, lambda **kw: '{"concepts": [], "prerequisites": []}')
        r = self._builder(cp_settings)._extract_concepts("some text")
        assert r["ok"] is True and r["concepts"] == []

    def test_valid_json_with_concepts_is_ok(self, cp_settings, monkeypatch):
        self._patch_llm(monkeypatch, lambda **kw: '{"concepts": [{"name": "force"}]}')
        r = self._builder(cp_settings)._extract_concepts("some text")
        assert r["ok"] is True and r["concepts"][0]["name"] == "force"

    def test_empty_response_is_not_ok(self, cp_settings, monkeypatch):
        self._patch_llm(monkeypatch, lambda **kw: "")
        assert self._builder(cp_settings)._extract_concepts("t")["ok"] is False

    def test_invalid_json_is_not_ok(self, cp_settings, monkeypatch):
        self._patch_llm(monkeypatch, lambda **kw: "not json at all")
        r = self._builder(cp_settings)._extract_concepts("t")
        assert r["ok"] is False and "invalid JSON" in r["error"]

    def test_a_raising_llm_is_not_ok(self, cp_settings, monkeypatch):
        def boom(**kw):
            raise RuntimeError("endpoint down")
        self._patch_llm(monkeypatch, boom)
        r = self._builder(cp_settings)._extract_concepts("t")
        assert r["ok"] is False and "endpoint down" in r["error"]

    def test_a_json_list_is_not_ok(self, cp_settings, monkeypatch):
        self._patch_llm(monkeypatch, lambda **kw: "[1, 2, 3]")
        assert self._builder(cp_settings)._extract_concepts("t")["ok"] is False


# ── build_graph: the failure count and resume ─────────────────────────────────

class TestBuildGraphFailureAccounting:
    def _wire(self, monkeypatch, results):
        """Replace the driver and the extractor; `results` is a list of ok flags."""
        monkeypatch.setattr(GraphBuilder, "_get_driver", lambda self: _FakeDriver())
        calls = {"n": 0}

        def fake_extract(self, text):
            i = calls["n"]
            calls["n"] += 1
            return _ok((f"concept-{i}",)) if results[i] else _fail(f"failure {i}")

        monkeypatch.setattr(GraphBuilder, "_extract_concepts", fake_extract)
        return calls

    def test_failed_chunks_are_counted(self, cp_settings, monkeypatch):
        chunks = _chunks(5)
        self._wire(monkeypatch, [True, True, False, True, True])
        stats = GraphBuilder(cp_settings).build_graph("doc-graph", "global", chunks)
        assert stats["failed_chunks"] == 1
        assert stats["chunk_nodes"] == 5
        assert stats["chunks_resumed"] == 0

    def test_all_failures_are_counted(self, cp_settings, monkeypatch):
        chunks = _chunks(4)
        self._wire(monkeypatch, [False, False, False, False])
        stats = GraphBuilder(cp_settings).build_graph("doc-graph", "global", chunks)
        assert stats["failed_chunks"] == 4

    def test_a_clean_run_reports_zero(self, cp_settings, monkeypatch):
        chunks = _chunks(3)
        self._wire(monkeypatch, [True, True, True])
        stats = GraphBuilder(cp_settings).build_graph("doc-graph", "global", chunks)
        assert stats["failed_chunks"] == 0

    def test_second_build_resumes_and_retries_only_the_failure(self, cp_settings, monkeypatch):
        """The resume contract: completed chunks are not re-extracted, the failed one is."""
        chunks = _chunks(5)
        calls = self._wire(monkeypatch, [True, True, False, True, True])
        GraphBuilder(cp_settings).build_graph("doc-graph", "global", chunks)
        assert calls["n"] == 5

        # Second pass: only the one failed chunk should be attempted.
        calls["n"] = 0
        monkeypatch.setattr(GraphBuilder, "_extract_concepts",
                            lambda self, text: _ok(("recovered",)))
        stats = GraphBuilder(cp_settings).build_graph("doc-graph", "global", chunks)
        assert stats["chunks_resumed"] == 4
        assert stats["failed_chunks"] == 0

    def test_resume_false_re_extracts_everything(self, cp_settings, monkeypatch):
        chunks = _chunks(3)
        calls = self._wire(monkeypatch, [True, True, True])
        GraphBuilder(cp_settings).build_graph("doc-graph", "global", chunks)
        calls["n"] = 0
        GraphBuilder(cp_settings).build_graph("doc-graph", "global", chunks, resume=False)
        assert calls["n"] == 3
