"""Tests for the late-chunk resume cache (``src/pdf_ingestion/embed_cache.py``).

The cache exists because Step 8's three runs each discarded a nearly-complete document — the last
after **339 of 341** parents (IMPROVEMENTS.md §I19). What has to be true for it to be safe:

1. **A hit reproduces the vectors exactly** — bit-for-bit, not approximately. A cache that returns
   subtly different vectors is worse than no cache, because nothing downstream can tell.
2. **A miss is always safe.** Any mismatch (child count, child ids, corrupt file, unreadable
   directory) degrades to re-embedding. The failure mode of the cache must never be a wrong index.
3. **The key actually invalidates.** A changed chunking knob or a different PDF must not find the
   old entries.
4. **The cache cannot fail a run.** Every write is best-effort and atomic.

Offline throughout: the cluster is an ``httpx.MockTransport``, the tokenizer a whitespace stand-in
(borrowed from ``test_late_chunk_embedder``).
"""
from __future__ import annotations

import numpy as np

from src.pdf_ingestion.embed_cache import CachedParent, EmbeddingCache, fingerprint
from src.pdf_ingestion.late_chunk_embedder import EnrichedChunk, LateChunkEmbedder
from tests.test_late_chunk_embedder import (
    DIM,
    DIM_LOW,
    PARENT_TEXT,
    FakeTokenizer,
    _cfg,
    _child,
    _mock_cluster,
    _parent,
)

# ── Fingerprint ────────────────────────────────────────────────────────────

def _pdf(tmp_path, name="doc.pdf", body=b"%PDF-1.4 test"):
    p = tmp_path / name
    p.write_bytes(body)
    return p


def test_fingerprint_is_stable_for_the_same_inputs(tmp_path):
    pdf = _pdf(tmp_path)
    cfg = _cfg()
    assert fingerprint(pdf, cfg) == fingerprint(pdf, cfg)


def test_fingerprint_changes_with_pdf_content(tmp_path):
    a = _pdf(tmp_path, "a.pdf", b"%PDF one")
    b = _pdf(tmp_path, "b.pdf", b"%PDF two")
    assert fingerprint(a, _cfg()) != fingerprint(b, _cfg())


def test_fingerprint_changes_with_each_chunking_knob(tmp_path):
    """Every field that moves a boundary or a vector must invalidate; otherwise a stale entry
    is silently reused after a config change."""
    pdf = _pdf(tmp_path)
    base = fingerprint(pdf, _cfg())
    for field, value in [
        ("parent_max_tokens", 1234),
        ("semantic_threshold", 0.5),
        ("min_chunk_tokens", 7),
        ("late_chunk_enabled", False),
        ("dense_model", "other/model"),
        # measured inert (see _FINGERPRINT_FIELDS) but carried as cheap insurance
        ("chunk_size", 128),
        ("chunk_overlap", 8),
    ]:
        assert fingerprint(pdf, _cfg(**{field: value})) != base, f"{field} did not invalidate"


def test_fingerprint_changes_with_the_schema_version(tmp_path, monkeypatch):
    """Config fields cannot capture a CODE change. Bumping the version must invalidate.

    Without this, a change to the chunker or the embedding path would keep reusing entries produced
    by the old code — silently wrong, which is the failure this whole module is built to avoid.
    """
    pdf = _pdf(tmp_path)
    base = fingerprint(pdf, _cfg())
    monkeypatch.setattr("src.pdf_ingestion.embed_cache._CACHE_SCHEMA_VERSION", 99)
    assert fingerprint(pdf, _cfg()) != base


def test_counters_are_exact_under_concurrency(tmp_path):
    """`get`/`put` run on up to N worker threads; `x += 1` is a read-modify-write.

    **This test does NOT discriminate on CPython 3.11, and that is recorded deliberately.** The
    reviewer flagged the unlocked counters, and it is theoretically right — but measured directly,
    an unlocked `+= 1` on an int attribute lost **zero** increments at 8x25, 16x150 and
    **32x300** with `sys.setswitchinterval(1e-6)`. The GIL plus the specializing interpreter make
    the read-modify-write complete within a time slice for this access pattern. An earlier version
    of this test appeared to fail against the unlocked counter; re-measured in isolation, it does
    not, so that observation is not relied on here.

    So what is this test for? Two things, both real:
      * a **free-threaded** Python (3.13+ without the GIL) makes this genuinely racy, and the lock
        is load-bearing there rather than decorative;
      * it pins the counts exactly, so a future refactor to a non-atomic counter (or to a shared
        dict of counters) fails here rather than in a log line nobody reads.

    The honest summary for the register: the lock is cheap insurance, and the *risk* is accepted
    rather than demonstrated.
    """
    import threading as _threading

    cache = EmbeddingCache(tmp_path, "key")
    parent = _parent()
    chunks = _chunks(parent, [(0, 10)])
    for pid in range(40):
        cache.put(pid, chunks)

    errors: list[BaseException] = []

    def hammer(pid: int) -> None:
        try:
            for _ in range(25):
                cache.get(pid)   # hit
                cache.get(999)   # miss
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [_threading.Thread(target=hammer, args=(pid,)) for pid in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert cache.hits == 8 * 25, f"lost increments: {cache.hits} != 200"
    assert cache.misses == 8 * 25, f"lost increments: {cache.misses} != 200"


# ── Round trip ─────────────────────────────────────────────────────────────

def _chunks(parent, texts_spans):
    return [
        EnrichedChunk(
            chunk=_child(i, PARENT_TEXT[s:e], s, e, parent),
            dense_1024=np.full(DIM, 0.1 * (i + 1), dtype=np.float32),
            dense_64=np.full(DIM_LOW, 0.2 * (i + 1), dtype=np.float32),
            model_name="Qwen/Qwen3-Embedding-0.6B",
            token_span=(i, i + 3),
            late_chunked=(i % 2 == 0),
        )
        for i, (s, e) in enumerate(texts_spans)
    ]


def test_round_trip_reproduces_the_vectors_exactly(tmp_path):
    cache = EmbeddingCache(tmp_path, "key")
    parent = _parent()
    original = _chunks(parent, [(0, 10), (10, 20)])

    cache.put(parent.parent_id, original)
    entry = cache.get(parent.parent_id)

    assert entry is not None
    assert entry.model_name == "Qwen/Qwen3-Embedding-0.6B"
    rebuilt = entry.rebuild([c.chunk for c in original])
    assert rebuilt is not None
    for before, after in zip(original, rebuilt):
        assert np.array_equal(before.dense_1024, after.dense_1024), "must be bit-identical"
        assert np.array_equal(before.dense_64, after.dense_64)
        assert before.token_span == after.token_span
        assert before.late_chunked == after.late_chunked
        assert before.chunk is after.chunk, "the chunk object must be the live one, not a copy"


def test_missing_entry_is_a_miss_not_an_error(tmp_path):
    cache = EmbeddingCache(tmp_path, "key")
    assert cache.get(0) is None
    assert cache.hits == 0 and cache.misses == 1


# ── Rebuild guards: a hit must never mis-join ──────────────────────────────

def test_rebuild_rejects_a_different_child_count(tmp_path):
    cache = EmbeddingCache(tmp_path, "key")
    parent = _parent()
    cache.put(parent.parent_id, _chunks(parent, [(0, 10), (10, 20)]))
    entry = cache.get(parent.parent_id)
    assert entry is not None
    shorter = [_child(0, PARENT_TEXT[0:10], 0, 10, parent)]
    assert entry.rebuild(shorter) is None


def _regenerate(children):
    """Same text and spans, brand-new chunk ids — exactly what a fresh chunker call produces."""
    from src.pdf_ingestion.chunker import TextChunk

    return [
        TextChunk(
            chunk_id=f"fresh-{i}-{id(c)}", document_id=c.chunk.document_id,
            tenant_id=c.chunk.tenant_id, chunk_index=c.chunk.chunk_index, text=c.chunk.text,
            char_start=c.chunk.char_start, char_end=c.chunk.char_end,
            token_count=c.chunk.token_count, page_number=c.chunk.page_number,
            parent_id=c.chunk.parent_id, parent_text=c.chunk.parent_text,
        )
        for i, c in enumerate(children)
    ]


def test_rebuild_hits_when_chunk_ids_are_regenerated(tmp_path):
    """THE PRODUCTION SHAPE: a fresh chunker call mints new chunk ids for identical content.

    ``chunk_id`` is ``str(uuid.uuid4())``, so a re-run of the pipeline produces different ids for
    the same children. The first version of this cache keyed on those ids, which meant it could
    never hit in production — and its tests passed anyway, because they reused the same child
    objects. This test builds the children the way the pipeline actually does: same text and spans,
    brand-new ids.
    """

    cache = EmbeddingCache(tmp_path, "key")
    parent = _parent()
    original = _chunks(parent, [(0, 10), (10, 20)])
    cache.put(parent.parent_id, original)

    regenerated = _regenerate(original)
    assert [c.chunk_id for c in regenerated] != [c.chunk.chunk_id for c in original]

    entry = cache.get(parent.parent_id)
    assert entry is not None
    rebuilt = entry.rebuild(regenerated)
    assert rebuilt is not None, "a regenerated id must NOT be treated as a miss"
    for i, (before, after) in enumerate(zip(original, rebuilt)):
        assert np.array_equal(before.dense_1024, after.dense_1024)
        assert after.chunk is regenerated[i], "vectors must attach to the LIVE child objects"


def test_rebuild_rejects_same_count_different_text(tmp_path):
    """A re-chunk can produce the same NUMBER of children with different content — the text is
    what is checked, because a count check alone would accept that and corrupt the index."""
    cache = EmbeddingCache(tmp_path, "key")
    parent = _parent()
    original = _chunks(parent, [(0, 10), (10, 20)])
    cache.put(parent.parent_id, original)

    impostors = [_child(0, "totally different text", 0, 10, parent),
                 _child(1, "also different", 10, 20, parent)]
    entry = cache.get(parent.parent_id)
    assert entry is not None
    assert entry.rebuild(impostors) is None


def test_rebuild_rejects_same_text_different_span(tmp_path):
    """Identical text at a different offset means different token context — not a valid hit."""
    cache = EmbeddingCache(tmp_path, "key")
    parent = _parent()
    original = _chunks(parent, [(0, 10)])
    cache.put(parent.parent_id, original)

    moved = [_child(0, original[0].chunk.text, 5, 15, parent)]
    entry = cache.get(parent.parent_id)
    assert entry is not None
    assert entry.rebuild(moved) is None


def test_corrupt_entry_is_a_miss_not_a_crash(tmp_path):
    cache = EmbeddingCache(tmp_path, "key")
    parent = _parent()
    cache.put(parent.parent_id, _chunks(parent, [(0, 10)]))
    (cache.directory / "p0.npz").write_bytes(b"not an npz at all")

    assert cache.get(0) is None
    assert cache.misses == 1


def test_put_never_raises_when_the_cache_is_unusable(tmp_path):
    """A cache is an optimisation: a broken one must degrade, not abort an ingest."""
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("I am a file, so mkdir under me fails")
    cache = EmbeddingCache(blocker, "key")
    cache.put(0, _chunks(_parent(), [(0, 10)]))  # must not raise
    assert cache.writes == 0


def test_cached_parent_dataclass_is_the_stored_shape(tmp_path):
    cache = EmbeddingCache(tmp_path, "key")
    cache.put(3, _chunks(_parent(), [(0, 10)]))
    entry = cache.get(3)
    assert isinstance(entry, CachedParent)
    assert entry.dense_1024.shape == (1, DIM)
    assert entry.dense_64.shape == (1, DIM_LOW)
    assert entry.token_spans.shape == (1, 2)


# ── Integration: a second pass does not re-embed ───────────────────────────

def _counting_embedder(cfg):
    """A mock cluster that counts per-token calls, so 'did it re-embed?' is observable."""
    embedder = _mock_cluster(cfg)
    real = embedder.embed_documents_tokens
    calls: list[str] = []

    def counted(texts):
        calls.extend(texts)
        return real(texts)

    embedder.embed_documents_tokens = counted
    return embedder, calls


def test_second_pass_re_embeds_nothing(tmp_path):
    """The whole point: a re-run after an abort must reuse the finished parents."""
    cfg = _cfg(late_chunk_workers=1)
    parents = [_parent(), _parent()]
    parents[1].parent_id = 1
    children = [
        _child(0, PARENT_TEXT[0:10], 0, 10, parents[0]),
        _child(1, PARENT_TEXT[0:10], 0, 10, parents[1]),
    ]
    cache = EmbeddingCache(tmp_path, "key")

    embedder, calls = _counting_embedder(cfg)
    emb = LateChunkEmbedder(settings=cfg, embedder=embedder, tokenizer=FakeTokenizer())
    first = emb.embed_children(parents, children, cache=cache)
    assert len(calls) == 2, "both parents embedded on a cold cache"
    assert cache.writes == 2

    embedder2, calls2 = _counting_embedder(cfg)
    emb2 = LateChunkEmbedder(settings=cfg, embedder=embedder2, tokenizer=FakeTokenizer())
    # Second pass with REGENERATED children — the production shape. Reusing the same objects here
    # is what let the original uuid-keyed bug through: the ids only agree if you cheat.
    fresh_children = _regenerate(first)
    second = emb2.embed_children(parents, fresh_children, cache=cache)

    assert calls2 == [], "a warm cache must make ZERO cluster calls"
    assert cache.hits == 2, "both parents served from the cache on the second pass"
    assert cache.misses == 2, "and the misses are the first pass's — no new misses"
    for i, (a, b) in enumerate(zip(first, second)):
        assert np.array_equal(a.dense_1024, b.dense_1024)
        assert a.token_span == b.token_span
        assert b.chunk is fresh_children[i], "vectors must attach to the LIVE regenerated children"


def test_partial_cache_only_embeds_the_missing_parent(tmp_path):
    """This is attempt 4's shape: 339 parents cached, the missing one embedded."""
    cfg = _cfg(late_chunk_workers=1)
    parents = [_parent(), _parent(), _parent()]
    for i, p in enumerate(parents):
        p.parent_id = i
    children = [_child(i, PARENT_TEXT[0:10], 0, 10, p) for i, p in enumerate(parents)]
    cache = EmbeddingCache(tmp_path, "key")

    # Pre-seed parents 0 and 2 as if a previous run had finished them.
    emb0 = LateChunkEmbedder(settings=cfg, embedder=_mock_cluster(cfg), tokenizer=FakeTokenizer())
    emb0._enrich_one(parents[0], [children[0]], cache)
    emb0._enrich_one(parents[2], [children[2]], cache)

    embedder, calls = _counting_embedder(cfg)
    emb = LateChunkEmbedder(settings=cfg, embedder=embedder, tokenizer=FakeTokenizer())
    out = emb.embed_children(parents, children, cache=cache)

    assert len(calls) == 1, "only the missing parent may be embedded"
    assert len(out) == 3, "and all three parents must still be present, in order"
    assert [e.chunk.parent_id for e in out] == [0, 1, 2]


def test_no_cache_means_no_directory_is_created(tmp_path):
    cfg = _cfg(late_chunk_workers=1)
    parent = _parent()
    child = _child(0, PARENT_TEXT[0:10], 0, 10, parent)
    emb = LateChunkEmbedder(
        settings=cfg, embedder=_mock_cluster(cfg), tokenizer=FakeTokenizer()
    )
    emb.embed_children([parent], [child], cache=None)
    assert list(tmp_path.iterdir()) == []


def test_prune_removes_other_fingerprints_only(tmp_path):
    stale = EmbeddingCache(tmp_path, "oldkey")
    stale.put(0, _chunks(_parent(), [(0, 10)]))
    current = EmbeddingCache(tmp_path, "newkey")
    current.put(0, _chunks(_parent(), [(0, 10)]))

    removed = current.prune()

    assert removed == ["oldkey"]
    assert current.get(0) is not None
    assert not (tmp_path / "oldkey").exists()


def test_concurrent_path_also_uses_the_cache(tmp_path):
    """The pooled path must hit the cache too — else attempt 4 re-embeds everything at 4 workers."""
    cfg = _cfg(late_chunk_workers=4)
    parents = [_parent()]
    for i in range(1, 5):
        p = _parent()
        p.parent_id = i
        parents.append(p)
    children = [_child(i, PARENT_TEXT[0:10], 0, 10, p) for i, p in enumerate(parents)]
    cache = EmbeddingCache(tmp_path, "key")

    embedder, calls = _counting_embedder(cfg)
    emb = LateChunkEmbedder(settings=cfg, embedder=embedder, tokenizer=FakeTokenizer())
    first = emb.embed_children(parents, children, cache=cache)
    assert len(calls) == 5

    embedder2, calls2 = _counting_embedder(cfg)
    emb2 = LateChunkEmbedder(settings=cfg, embedder=embedder2, tokenizer=FakeTokenizer())
    out = emb2.embed_children(parents, _regenerate(first), cache=cache)
    assert calls2 == [], "the concurrent path must serve from cache"
    assert len(out) == 5
    assert [e.chunk.parent_id for e in out] == [0, 1, 2, 3, 4]
