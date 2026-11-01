"""Tests for the E3 late-chunk embedder (``src/pdf_ingestion/late_chunk_embedder.py``).

Offline (the default): the cluster is an ``httpx.MockTransport`` that emits a per-token matrix
with the **measured endpoint contract** — exactly one extra trailing special-token vector — and
the tokenizer is a whitespace stand-in with an HF-fast call signature. That pins the four
things the module turns on:

1. a child's vector is the mean of the parent's token vectors **inside the child's char span**;
2. the trailing special vector is dropped (and a wrong count raises rather than shifting spans);
3. a span overlapping no token falls back to the parent mean, loudly;
4. ``mean(tok)[:64] == mean(tok[:64])`` — the MRL/linearity claim the plan leans on.

One ``slow`` test runs the **real** Qwen3 tokenizer against the **real** cluster and asserts
the plan's Step 4 acceptance: a chunk containing "This" gets a vector that differs from its
isolation-embedded twin.
"""
from __future__ import annotations

import re

import httpx
import numpy as np
import pytest

from src.core.config import Settings
from src.pdf_ingestion.chunker import TextChunk
from src.pdf_ingestion.cluster_embedder import ClusterDenseEmbedder, mrl_slice
from src.pdf_ingestion.late_chunk_embedder import (
    EnrichedChunk,
    LateChunkEmbedder,
    declared_specials,
)
from src.pdf_ingestion.models import ParentChunk

URL = "http://cluster.test/embed-text/v1/embeddings"
# The live cluster endpoint (HANDOFF "Verified facts": 10.0.10.70:8123 serves the embed lane).
LIVE_EMBED_URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"
DIM = 32          # small: the tests recompute the expected means themselves
DIM_LOW = 8


# ── Fakes: HF-fast-like tokenizer, endpoint-like transport ────────────────────

class FakeTokenizer:
    """Whitespace tokenizer with the HF-fast ``__call__`` signature the module uses."""

    def __call__(self, text, add_special_tokens=True, return_offsets_mapping=False):
        offsets = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
        out: dict = {"input_ids": list(range(len(offsets)))}
        if return_offsets_mapping:
            out["offset_mapping"] = offsets
        return out


def _token_strings(text: str) -> list[str]:
    return [m.group(0) for m in re.finditer(r"\S+", text)]


def _token_vector(token: str) -> np.ndarray:
    """Deterministic unit vector for a token — the fake endpoint's unit.

    ⚠️ Independent of POSITION on purpose: a document prefix shifts every token index, and the
    span-invariance guard asserts a child's pooled vector is unchanged by the prefix. A
    position-aware vector would make that guard fail for the wrong reason.
    """
    rng = np.random.default_rng(abs(hash(token)) % (2**31))
    v = rng.random(DIM).astype(np.float32)
    return v / (np.linalg.norm(v) + 1e-9)


def _expected_matrix(text: str, extra: int = 1) -> np.ndarray:
    """The matrix the fake endpoint returns: one vector per token, plus ``extra`` trailing."""
    vecs = [_token_vector(t) for t in _token_strings(text)]
    vecs += [_token_vector("<|endoftext|>") for _ in range(extra)]
    return np.asarray(vecs, dtype=np.float32)


def _mock_cluster(settings: Settings, extra: int = 1) -> ClusterDenseEmbedder:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        body = json.loads(request.content.decode())
        if body.get("return_token_embeddings") is True:
            data = [
                {"index": i, "embedding": [_expected_matrix(t, extra).tolist()]}
                for i, t in enumerate(body["input"])
            ]
        else:  # pooled path (the isolation twin)
            data = [
                {"index": i, "embedding": _expected_matrix(t)[:-1].mean(axis=0).tolist()}
                for i, t in enumerate(body["input"])
            ]
        return httpx.Response(200, json={"data": data})

    return ClusterDenseEmbedder(
        settings=settings, client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def _cfg(**over) -> Settings:
    base: dict = dict(
        sv_embed_url=URL,
        dense_model="Qwen/Qwen3-Embedding-0.6B",
        dense_dim=DIM,
        dense_dim_low=DIM_LOW,
        query_instruction="Instruct: test\nQuery: ",
        embedding_batch_size=8,
        late_chunk_enabled=True,
    )
    base.update(over)
    return Settings(**base)


def _embedder(cfg: Settings, extra: int = 1) -> LateChunkEmbedder:
    return LateChunkEmbedder(
        settings=cfg, embedder=_mock_cluster(cfg, extra), tokenizer=FakeTokenizer()
    )


PARENT_TEXT = (
    "The lever is a rigid bar that rotates about a fulcrum. "
    "This is the simplest machine of all. "
    "The mechanical advantage equals the ratio of the two arms."
)


def _child(idx: int, text: str, start: int, end: int, parent: ParentChunk) -> TextChunk:
    return TextChunk(
        chunk_id=f"c{idx}", document_id="doc", tenant_id="global", chunk_index=idx,
        text=text, char_start=start, char_end=end, token_count=len(text.split()),
        page_number=1, parent_id=parent.parent_id, parent_text=parent.text,
    )


def _parent() -> ParentChunk:
    return ParentChunk(parent_id=0, text=PARENT_TEXT, page_map={0: 1})


# ── 1. Span → tokens → mean ──────────────────────────────────────────────────

def test_child_vector_is_the_mean_of_its_token_vectors():
    cfg = _cfg()
    parent = _parent()
    s, e = 0, PARENT_TEXT.index("This")
    children = [
        _child(0, PARENT_TEXT[s:e].strip(), s, e, parent),
        _child(1, PARENT_TEXT[e:].strip(), e, len(PARENT_TEXT), parent),
    ]

    out = _embedder(cfg).embed_parent(parent, children)

    assert len(out) == 2
    matrix = _expected_matrix(PARENT_TEXT)[:-1]          # content tokens only
    offsets = FakeTokenizer()(PARENT_TEXT, add_special_tokens=False,
                              return_offsets_mapping=True)["offset_mapping"]
    for enriched, (cs, ce) in zip(out, [(s, e), (e, len(PARENT_TEXT))]):
        idx = [i for i, (ts, te) in enumerate(offsets) if te > cs and ts < ce]
        expected = matrix[idx].mean(axis=0)
        expected /= np.linalg.norm(expected) + 1e-9
        assert np.allclose(enriched.dense_1024, expected, atol=1e-5)
        assert enriched.token_span == (idx[0], idx[-1] + 1)
        assert enriched.late_chunked is True


def test_the_trailing_special_vector_is_not_pooled():
    """The endpoint's last vector is the special token — pooling it would bias every child."""
    cfg = _cfg()
    parent = _parent()
    s, e = 0, len(PARENT_TEXT)
    child = _child(0, PARENT_TEXT, s, e, parent)

    out = _embedder(cfg).embed_parent(parent, [child])[0]

    with_special = _expected_matrix(PARENT_TEXT).mean(axis=0)      # if the vector leaked in
    content_only = _expected_matrix(PARENT_TEXT)[:-1].mean(axis=0)  # what the module must do
    content_only /= np.linalg.norm(content_only) + 1e-9
    assert np.allclose(out.dense_1024, content_only, atol=1e-5)
    assert not np.allclose(out.dense_1024, with_special, atol=1e-5)
    assert out.token_span[1] == len(_token_strings(PARENT_TEXT))


# ── 2. Alignment failures are loud ───────────────────────────────────────────

def test_token_count_mismatch_raises():
    cfg = _cfg()
    parent = _parent()
    child = _child(0, PARENT_TEXT, 0, len(PARENT_TEXT), parent)

    emb = _embedder(cfg, extra=3)  # 2 vectors too many
    with pytest.raises(ValueError, match="alignment"):
        emb.embed_parent(parent, [child])


def test_wrong_dimension_raises():
    cfg = _cfg()
    parent = _parent()
    child = _child(0, PARENT_TEXT, 0, len(PARENT_TEXT), parent)

    class WrongDim:
        model_name = "wrong"

        def embed_documents_tokens(self, texts):
            return [np.zeros((len(_token_strings(texts[0])) + 1, DIM + 1), dtype=np.float32)]

        def embed_documents(self, texts):
            return [np.zeros(DIM, dtype=np.float32) for _ in texts]

        def embed_query(self, text):
            return np.zeros(DIM, dtype=np.float32)

    with pytest.raises(ValueError, match="expected"):
        emb = LateChunkEmbedder(settings=cfg, embedder=WrongDim(), tokenizer=FakeTokenizer())
        emb.embed_parent(parent, [child])


def test_span_overlapping_no_token_falls_back_to_the_parent_mean():
    cfg = _cfg()
    parent = _parent()
    # A degenerate zero-width span past the last token overlaps nothing (the shape an empty or
    # trailing child has). NB an interior zero-width span DOES match the token containing it —
    # the overlap test `te > start and ts < end` is the class repo's, kept deliberately.
    end = len(PARENT_TEXT)
    child = _child(0, "", end, end, parent)

    out = _embedder(cfg).embed_parent(parent, [child])[0]

    matrix = _expected_matrix(PARENT_TEXT)[:-1]
    expected = matrix.mean(axis=0)
    expected /= np.linalg.norm(expected) + 1e-9
    assert np.allclose(out.dense_1024, expected, atol=1e-5)
    assert out.token_span == (0, 0)


# ── 3. MRL: the linearity claim ──────────────────────────────────────────────

def test_dense_64_is_the_mean_of_the_first_64_coordinates():
    """mean(tok)[:64] == mean(tok[:64]) — late chunking and MRL compose (plan §2.1)."""
    cfg = _cfg()
    parent = _parent()
    child = _child(0, PARENT_TEXT, 0, len(PARENT_TEXT), parent)

    out = _embedder(cfg).embed_parent(parent, [child])[0]

    matrix = _expected_matrix(PARENT_TEXT)[:-1]
    assert np.allclose(out.dense_64, mrl_slice(matrix[:, :DIM_LOW].mean(axis=0), DIM_LOW),
                       atol=1e-5)
    assert out.dense_64.shape == (DIM_LOW,)
    assert np.isclose(np.linalg.norm(out.dense_64), 1.0, atol=1e-5)


# ── 4. Isolation twin and grouping ───────────────────────────────────────────

def test_disabled_flag_embeds_children_in_isolation():
    cfg = _cfg(late_chunk_enabled=False)
    parent = _parent()
    children = [_child(0, PARENT_TEXT, 0, len(PARENT_TEXT), parent)]

    out = _embedder(cfg).embed_parent(parent, children)[0]

    assert out.late_chunked is False
    assert out.token_span == (0, 0)
    assert out.dense_1024.shape == (DIM,)


def test_embed_children_groups_by_parent_and_keeps_document_order():
    cfg = _cfg()
    parents = [_parent(), ParentChunk(parent_id=1, text=PARENT_TEXT, page_map={0: 2})]
    children = [
        _child(0, PARENT_TEXT, 0, 10, parents[0]),
        _child(1, PARENT_TEXT, 0, 10, parents[1]),
        _child(2, PARENT_TEXT, 10, 20, parents[0]),
    ]

    out = _embedder(cfg).embed_children(parents, children)

    assert [e.chunk.chunk_index for e in out] == [0, 2, 1]  # parent 0's children, then parent 1's
    assert [e.chunk.parent_id for e in out] == [0, 0, 1]


def test_orphan_child_raises():
    cfg = _cfg()
    parent = _parent()
    orphan = _child(0, PARENT_TEXT, 0, 10, parent)
    orphan.parent_id = 99

    with pytest.raises(ValueError, match="do not exist"):
        _embedder(cfg).embed_children([parent], [orphan])


def test_empty_parent_is_skipped():
    cfg = _cfg()
    empty = ParentChunk(parent_id=3, text="   ", page_map={0: 1})
    child = _child(0, "", 0, 0, empty)
    assert _embedder(cfg).embed_parent(empty, [child]) == []


def test_parent_that_tokenizes_to_zero_tokens_falls_back_to_isolation():
    """Regression: this branch called a method that does not exist (found by the verifier)."""
    class EmptyTokenizer(FakeTokenizer):
        def __call__(self, text, add_special_tokens=True, return_offsets_mapping=False):
            out = super().__call__(text, add_special_tokens, return_offsets_mapping)
            out["offset_mapping"] = []
            return out

    cfg = _cfg()
    parent = _parent()
    child = _child(0, PARENT_TEXT, 0, len(PARENT_TEXT), parent)

    emb = LateChunkEmbedder(
        settings=cfg, embedder=_mock_cluster(cfg), tokenizer=EmptyTokenizer()
    )
    out = emb.embed_parent(parent, [child])[0]

    assert out.late_chunked is False
    assert out.token_span == (0, 0)
    assert out.dense_1024.shape == (DIM,)


def test_enriched_chunk_wraps_the_child_unchanged():
    cfg = _cfg()
    parent = _parent()
    child = _child(0, PARENT_TEXT, 0, 10, parent)
    out = _embedder(cfg).embed_parent(parent, [child])[0]
    assert isinstance(out, EnrichedChunk)
    assert out.chunk is child
    assert out.model_name == "Qwen/Qwen3-Embedding-0.6B"


# ── 5. Concurrency (plan Step 8 fix, §I16) ───────────────────────────────────

def _many_parents_children(n: int = 6):
    parents = [ParentChunk(parent_id=i, text=PARENT_TEXT, page_map={0: i + 1}) for i in range(n)]
    children: list[TextChunk] = []
    idx = 0
    for parent in parents:
        for start, end in ((0, 12), (12, 24)):
            children.append(_child(idx, PARENT_TEXT[start:end], start, end, parent))
            idx += 1
    return parents, children


def test_worker_count_does_not_change_the_output():
    """Concurrency changes the wall clock, not the result or its order.

    ``embed_children`` reassembles by parent position, so the document order the store and
    every other test depend on must be byte-identical between the serial and pooled paths.
    """
    parents, children = _many_parents_children()
    serial = _embedder(_cfg(late_chunk_workers=1)).embed_children(parents, children)
    pooled = _embedder(_cfg(late_chunk_workers=4)).embed_children(parents, children)

    assert [e.chunk.chunk_id for e in pooled] == [e.chunk.chunk_id for e in serial]
    assert [e.chunk.parent_id for e in pooled] == [e.chunk.parent_id for e in serial]
    for a, b in zip(serial, pooled):
        assert a.token_span == b.token_span
        assert np.allclose(a.dense_1024, b.dense_1024, atol=1e-6)
        assert np.allclose(a.dense_64, b.dense_64, atol=1e-6)


def test_workers_overlap_the_cluster_wait():
    """The pool must genuinely run parents in parallel — this phase is ~100% cluster wait."""
    import time as _time

    cfg = _cfg(late_chunk_workers=6)
    parents, children = _many_parents_children(6)
    slow = _mock_cluster(cfg)
    real = slow.embed_documents_tokens

    def delayed(texts):
        _time.sleep(0.25)
        return real(texts)

    slow.embed_documents_tokens = delayed
    emb = LateChunkEmbedder(settings=cfg, embedder=slow, tokenizer=FakeTokenizer())

    t0 = _time.time()
    out = emb.embed_children(parents, children)
    elapsed = _time.time() - t0

    assert len(out) == 12
    # 6 parents x 0.25 s serial = 1.5 s; with 6 workers ~0.25 s. Generous slack for CI.
    assert elapsed < 0.9, f"parents did not overlap (took {elapsed:.2f}s)"


def test_a_failing_parent_aborts_loudly_instead_of_shrinking_the_document():
    """``future.result()`` re-raises: a lost parent must not silently reduce the chunk count."""
    cfg = _cfg(late_chunk_workers=4)
    parents, children = _many_parents_children(4)
    broken = _mock_cluster(cfg)

    def explode(texts):
        raise httpx.ReadTimeout("timed out", request=httpx.Request("POST", URL))

    broken.embed_documents_tokens = explode
    emb = LateChunkEmbedder(settings=cfg, embedder=broken, tokenizer=FakeTokenizer())

    with pytest.raises(httpx.ReadTimeout):
        emb.embed_children(parents, children)


def test_tokenizer_is_resolved_before_the_pool_starts(monkeypatch):
    """The lazy tokenizer load must not race the workers.

    ``_get_tokenizer`` guards with a bare ``if self._tokenizer is None``, so N workers starting
    together could each build the model. The pool path warms it first; this pins that ordering,
    because the failure it prevents (several concurrent model loads) is silent and only shows up
    as wasted work and cache-lock contention.
    """
    cfg = _cfg(late_chunk_workers=8)
    parents, children = _many_parents_children(8)
    emb = _embedder(cfg)

    order: list[str] = []
    real_get = emb._get_tokenizer
    monkeypatch.setattr(
        emb, "_get_tokenizer", lambda: (order.append("tokenizer"), real_get())[1]
    )
    real_parent = emb.embed_parent

    def observed_parent(parent, kids):
        order.append("parent")
        return real_parent(parent, kids)

    monkeypatch.setattr(emb, "embed_parent", observed_parent)

    emb.embed_children(parents, children)

    assert order[0] == "tokenizer", (
        "the tokenizer must be resolved before any parent is embedded, "
        f"otherwise the workers race its lazy load (got {order[:3]})"
    )
    assert order.count("parent") == len(parents)


# ── 5b. The document prefix and the model-aware special layout (plan §1 traps 1–3) ──

def test_declared_specials_are_model_specific_and_refuse_unknowns():
    """trap 3: the endpoint's special-token layout is a property of the MODEL, and an unknown
    model is refused rather than assumed to follow the Qwen3 contract."""
    assert declared_specials("nomic-ai/nomic-embed-text-v1.5") == (0, 2)
    assert declared_specials("Qwen/Qwen3-Embedding-0.6B") == (0, 1)
    with pytest.raises(ValueError, match="declared special-token layout"):
        declared_specials("some/unknown-model")


def test_content_tokens_drops_the_declared_wrapper():
    """nomic adds TWO trailing specials; Qwen3 one; a BERT-style layout is leading + trailing."""
    matrix = np.arange(30, dtype=np.float32).reshape(10, 3)
    nomic = LateChunkEmbedder._content_tokens(matrix, 8, 0, 3, (0, 2))
    assert np.array_equal(nomic, matrix[:8])             # two trailing dropped
    bert = LateChunkEmbedder._content_tokens(matrix, 8, 0, 3, (1, 1))
    assert np.array_equal(bert, matrix[1:9])             # one leading, one trailing
    with pytest.raises(ValueError, match="alignment"):   # an unexplained count is loud, not a shift
        LateChunkEmbedder._content_tokens(matrix, 9, 0, 3, (0, 2))


def test_a_document_prefix_does_not_shift_a_childs_pooling_window():
    """trap 2, the silent one: the prefix must move with BOTH the tokenization and the endpoint
    input, so each child still pools the SAME parent tokens and its span moves by exactly the
    prefix's token count. A missing shift pools the wrong tokens and NOTHING raises."""
    raw = _cfg()                                       # no prefix (Qwen3)
    pref = _cfg(document_prefix="search_document: ")   # nomic
    parent = _parent()
    s, e = 0, PARENT_TEXT.index("This")
    children = [
        _child(0, PARENT_TEXT[s:e].strip(), s, e, parent),
        _child(1, PARENT_TEXT[e:].strip(), e, len(PARENT_TEXT), parent),
    ]

    a = _embedder(raw).embed_parent(parent, children)
    b = _embedder(pref).embed_parent(parent, children)

    n_prefix = len(FakeTokenizer()(
        "search_document:", add_special_tokens=False, return_offsets_mapping=True
    )["offset_mapping"])
    assert n_prefix >= 1
    for x, y in zip(a, b):
        assert np.allclose(x.dense_1024, y.dense_1024, atol=1e-6)   # the SAME tokens pooled
        assert np.allclose(x.dense_64, y.dense_64, atol=1e-6)
        assert y.token_span == (x.token_span[0] + n_prefix, x.token_span[1] + n_prefix)


# ── 6. Live (slow): the plan's Step 4 acceptance check ───────────────────────

@pytest.mark.slow
def test_live_late_chunked_vector_differs_from_its_isolation_twin():
    """Real Qwen3 tokenizer + real cluster.

    The child opens with "This", so its antecedent is in the parent but not in the child. The
    late-chunked vector must therefore differ from the isolation embedding of the same text —
    that difference *is* the E3 fix. Also asserts the alignment precondition holds end-to-end.
    """
    import os

    from transformers import AutoTokenizer

    from src.pdf_ingestion.cluster_embedder import ClusterDenseEmbedder

    # conftest forces USE_STUB_EMBEDDER=true for the suite; this test is the live exception.
    cfg = Settings(
        use_stub_embedder=False,
        sv_embed_url=os.environ.get("SV_EMBED_URL", LIVE_EMBED_URL),
        dense_dim=1024,
        dense_dim_low=64,
        late_chunk_enabled=True,
    )
    try:
        tok = AutoTokenizer.from_pretrained(cfg.dense_model, cache_dir=cfg.model_cache_dir)
        embedder = ClusterDenseEmbedder(settings=cfg)
    except Exception as exc:  # noqa: BLE001 — a live probe: report, don't fail the suite
        pytest.skip(f"live cluster/tokenizer unavailable: {exc}")

    parent = ParentChunk(
        parent_id=0,
        text=(
            "The lever is a rigid bar that rotates about a fulcrum. "
            "This is the simplest machine of all, and it trades force for distance."
        ),
        page_map={0: 1},
    )
    start = parent.text.index("This")
    child = _child(0, parent.text[start:], start, len(parent.text), parent)

    emb = LateChunkEmbedder(settings=cfg, embedder=embedder, tokenizer=tok)
    try:
        late = emb.embed_parent(parent, [child])[0]
        isolated = emb.embed_isolated(child)
    except httpx.HTTPError as exc:
        pytest.skip(f"live cluster unreachable: {exc}")

    assert late.late_chunked and late.token_span[0] > 0
    assert late.dense_1024.shape == (cfg.dense_dim,)
    assert late.dense_64.shape == (cfg.dense_dim_low,)
    cos = float(np.dot(late.dense_1024, isolated.dense_1024))
    assert cos < 0.999, f"late-chunked vector is not distinguishable from isolation (cos={cos})"


# ── The isolation twin, BATCHED — the Shape B `--pooled` re-embed path (§I88) ─

def test_isolated_batch_is_pooled_over_each_chunks_own_text():
    """``embed_isolated_batch`` IS the pooled construction: whole-chunk text, prefixed, pooled.

    This is the path ``reembed_chunks.py --pooled`` writes into v3's dense lanes, so the guard is
    that each vector equals a manual pooled mean of the chunk's **own** text — not of its parent's
    span. Dropping the document prefix on the batch path, or the wrong special-token count,
    changes it.
    """
    cfg = _cfg(document_prefix="search_document: ")
    parent = _parent()
    children = [
        _child(0, "The lever is a rigid bar.", 0, 26, parent),
        _child(1, "The mechanical advantage equals the ratio.", 60, 99, parent),
    ]

    out = _embedder(cfg).embed_isolated_batch(children)

    assert [ec.chunk.chunk_id for ec in out] == ["c0", "c1"]
    for ec, child in zip(out, children):
        assert ec.late_chunked is False and ec.token_span == (0, 0)
        assert ec.dense_1024.shape == (DIM,) and ec.dense_64.shape == (DIM_LOW,)
        expected = _expected_matrix(cfg.document_prefix + child.text)[:-1].mean(axis=0)
        expected = expected / (np.linalg.norm(expected) + 1e-9)
        assert float(np.dot(ec.dense_1024, expected)) > 0.999999


def test_isolated_batch_ignores_the_parent_span():
    """Pooled ignores ``char_start``/``char_end``: the same text pooled twice is the same vector.

    This is the whole of the *drop late chunking* treatment — the late-chunk path pools the
    parent's tokens **inside the child's span**, so the same text at two different spans yields two
    different vectors. Under this path they must be identical.
    """
    cfg = _cfg(document_prefix="search_document: ")
    parent = _parent()
    a = _child(0, "The mechanical advantage", 60, 84, parent)
    b = _child(1, "The mechanical advantage", 0, 24, parent)   # same text, different span

    out = _embedder(cfg).embed_isolated_batch([a, b])

    assert float(np.dot(out[0].dense_1024, out[1].dense_1024)) > 0.999999


def test_isolated_batch_equals_isolated_one_at_a_time():
    """Batching changes only the request count, never a vector — the claim ``--pooled`` rests on."""
    cfg = _cfg(document_prefix="search_document: ")
    parent = _parent()
    children = [_child(i, t, 0, len(t), parent) for i, t in
                enumerate(["alpha beta gamma", "delta epsilon", "zeta eta theta"])]
    emb = _embedder(cfg)

    batched = emb.embed_isolated_batch(children)
    singles = [emb.embed_isolated(c) for c in children]

    assert len(batched) == len(singles) == 3
    for b, s in zip(batched, singles):
        assert np.allclose(b.dense_1024, s.dense_1024, atol=1e-6)
        assert np.allclose(b.dense_64, s.dense_64, atol=1e-6)


def test_isolated_batch_empty_is_empty():
    assert _embedder(_cfg()).embed_isolated_batch([]) == []
