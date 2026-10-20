"""Tests for the card-generation checkpoint + resume (IMPROVEMENTS.md §I27).

The defect these pin: `generate_cards_for_chunks` held every card in memory and
`DocumentStore.save_cards` wrote once, at the end. There is no resume and no cards-only rebuild
flag, so an abort at chunk 3,700 of 3,791 discarded the entire card run — ~10.6 h at the only
measured-healthy concurrency (§I26).

The three things that must hold, and each is a test below:

1. a re-run **skips** the chunks the previous run checkpointed, and still returns their cards;
2. a chunk whose card types **failed** is NOT treated as done (otherwise a run aborted during an
   endpoint outage resumes having "completed" the chunks that timed out — §I25 baked into the
   checkpoint);
3. the checkpoint is keyed on the (document, chunk set, card types, model) it was produced for,
   and the key is checked **on read**, not only in the file name (§I19a).

All offline: the LLM is replaced by a call-counting fake.
"""
from __future__ import annotations

import json
import uuid

import pytest

from src.core.config import Settings
from src.pdf_ingestion.card_checkpoint import CardCheckpoint, run_key
from src.pdf_ingestion.card_generator import (
    CardType,
    GeneratedCard,
    OllamaCardGenerator,
    _cards_from_dicts,
)
from src.pdf_ingestion.chunker import TextChunk

DOC = "7ba61432-c5e0-416d-aecf-25a232523481"
MODEL = "openai/gpt-oss-20b"
TYPES = [ct.value for ct in CardType]


def _chunks(n: int) -> list[TextChunk]:
    return [
        TextChunk(
            chunk_id=f"chunk-{i:04d}", document_id=DOC, tenant_id="global",
            chunk_index=i, text=f"text {i}", char_start=i * 10, char_end=i * 10 + 9,
            token_count=5, page_number=1,
        )
        for i in range(n)
    ]


def _card(chunk: TextChunk, ct: CardType) -> GeneratedCard:
    return GeneratedCard(
        card_id=str(uuid.uuid4()), chunk_id=chunk.chunk_id, document_id=chunk.document_id,
        tenant_id=chunk.tenant_id, card_type=ct.value, title="t", content="c",
    )


def _settings(tmp_path, **over) -> Settings:
    base = dict(
        llm_backend="openai", openai_model=MODEL, openai_api_base="http://cluster.test:8000",
        card_gen_workers=2, card_checkpoint_enabled=True,
        card_checkpoint_dir=str(tmp_path / "card_cache"),
    )
    base.update(over)
    return Settings(**base)


def _generator(settings: Settings, fail_for: set[str] | None = None):
    """A real generator with the LLM replaced by a call-counting fake.

    Built with `__new__` so the instructor client is never constructed — this test must not
    depend on config.yaml or a reachable endpoint.
    """
    gen = OllamaCardGenerator.__new__(OllamaCardGenerator)
    gen._cfg = settings
    gen._prompts = {ct: "prompt template" for ct in CardType}
    gen._parser = None
    gen._instructor_client = None
    gen.calls = []
    fail_for = fail_for or set()

    def fake_one(chunk: TextChunk, ct: CardType):
        gen.calls.append((chunk.chunk_index, ct.value))
        if chunk.chunk_id in fail_for:
            raise RuntimeError("simulated timeout")
        return [_card(chunk, ct)]

    gen._generate_one_type = fake_one
    return gen


# ── The checkpoint file ────────────────────────────────────────────────────

def test_records_round_trip_and_resume_skips_them(tmp_path):
    chunks = _chunks(5)
    cp = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    for c in chunks[:3]:
        cp.record(c.chunk_id, c.chunk_index, [_card(c, CardType.SUMMARY)], [])
    cp.close()

    again = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    assert again.done == {c.chunk_id for c in chunks[:3]}
    assert again.resumed_chunks == 3
    assert len(again.cards) == 3
    assert again.cards[0]["card_type"] == CardType.SUMMARY.value
    assert again.path == cp.path


def test_a_chunk_with_a_failed_card_type_is_not_treated_as_done(tmp_path):
    chunks = _chunks(3)
    cp = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    cp.record(chunks[0].chunk_id, 0, [_card(chunks[0], CardType.SUMMARY)], [])
    cp.record(chunks[1].chunk_id, 1, [], ["question", "factoid"])
    cp.close()

    again = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    assert again.done == {chunks[0].chunk_id}
    assert again.retried_chunks == 1
    assert chunks[1].chunk_id not in again.done


def test_the_key_covers_the_document_the_types_and_the_model():
    a = run_key(DOC, TYPES, MODEL)
    assert a == run_key(DOC, TYPES, MODEL)
    assert a != run_key("another-doc", TYPES, MODEL)
    assert a != run_key(DOC, TYPES[:4], MODEL)
    assert a != run_key(DOC, TYPES, "openai/gpt-oss-120b")
    # Type order must not matter.
    assert a == run_key(DOC, list(reversed(TYPES)), MODEL)


def test_entries_for_chunks_not_in_the_corpus_are_ignored(tmp_path):
    """A re-ingest regenerates chunk ids; stale entries must not be resumed OR written."""
    chunks = _chunks(4)
    cp = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    cp.record(chunks[0].chunk_id, 0, [_card(chunks[0], CardType.SUMMARY)], [])
    cp.close()

    # Same document and model, a corpus whose chunk ids are all new — what a re-ingest produces.
    reingested = [c.chunk_id + "-v2" for c in chunks]
    again = CardCheckpoint.open(tmp_path, DOC, reingested, TYPES, MODEL)

    assert again.path == cp.path, "the run key is the document, not the chunk list"
    assert again.done == set()
    assert again.cards == [], "cards for vanished chunks must not reach save_cards"
    assert again.ignored_chunks == 1


def test_a_resume_after_a_narrower_chunk_filter_still_works(tmp_path):
    """The other direction: a subset run must not invalidate the wider one's entries."""
    chunks = _chunks(6)
    cp = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    for c in chunks:
        cp.record(c.chunk_id, c.chunk_index, [], [])
    cp.close()

    subset = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks[:3]], TYPES, MODEL)
    assert subset.done == {c.chunk_id for c in chunks[:3]}
    # The three entries outside the subset are reported and dropped, not resumed.
    assert subset.ignored_chunks == 3


def test_the_header_is_checked_on_read_not_only_in_the_name(tmp_path):
    """§I19a: a file that loads but was written for something else must be an honest miss."""
    chunks = _chunks(3)
    cp = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    cp.record(chunks[0].chunk_id, 0, [], [])
    cp.close()

    # Rewrite the header's model to something else, leaving the file name untouched.
    lines = cp.path.read_text().splitlines()
    header = json.loads(lines[0])
    header["model"] = "some-other-model"
    cp.path.write_text("\n".join([json.dumps(header)] + lines[1:]) + "\n")

    again = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    assert again.done == set(), "a mismatched header must not be resumed"


def test_a_torn_final_line_costs_one_chunk_not_the_file(tmp_path):
    chunks = _chunks(4)
    cp = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    for c in chunks[:3]:
        cp.record(c.chunk_id, c.chunk_index, [], [])
    cp.close()

    with cp.path.open("a") as fh:
        fh.write('{"kind":"chunk","chunk_id":"chunk-0003","car')  # truncated mid-write

    again = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    assert again.done == {c.chunk_id for c in chunks[:3]}
    # The fragment is gone, so the next append cannot be preceded by garbage.
    assert not again.path.read_text().rstrip().endswith("car")

    again.record(chunks[3].chunk_id, 3, [], [])
    again.close()
    third = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    assert third.done == {c.chunk_id for c in chunks}


def test_fresh_discards_an_existing_checkpoint(tmp_path):
    chunks = _chunks(2)
    cp = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL)
    cp.record(chunks[0].chunk_id, 0, [], [])
    cp.close()

    fresh = CardCheckpoint.open(tmp_path, DOC, [c.chunk_id for c in chunks], TYPES, MODEL,
                                fresh=True)
    assert fresh.done == set()


def test_cards_from_dicts_drops_unknown_fields_instead_of_raising():
    rows = [{"chunk_id": "a", "card_type": "summary", "title": "t", "content": "c",
             "card_id": "1", "document_id": DOC, "tenant_id": "global",
             "something_from_the_future": 1}]
    cards = _cards_from_dicts(rows)
    assert len(cards) == 1 and cards[0].content == "c"
    # A row with nothing recognisable is skipped, not fatal.
    assert _cards_from_dicts([{"nonsense": True}, rows[0]]) == cards


# ── The generator ──────────────────────────────────────────────────────────

def test_a_second_run_makes_no_llm_calls_for_checkpointed_chunks(tmp_path):
    chunks = _chunks(4)
    settings = _settings(tmp_path)

    first = _generator(settings)
    cards_a = first.generate_cards_for_chunks(chunks)
    assert len(cards_a) == 4 * len(CardType)
    assert len(first.calls) == 4 * len(CardType)
    assert first.last_run_stats["chunks_resumed"] == 0
    assert first.last_run_stats["failed_card_types"] == {}

    second = _generator(settings)
    cards_b = second.generate_cards_for_chunks(chunks)

    assert second.calls == [], "a resumed run must issue no LLM calls"
    assert second.last_run_stats["chunks_resumed"] == 4
    assert len(cards_b) == len(cards_a), "resumed cards must still be returned for the write"


def test_only_the_missing_chunks_are_regenerated(tmp_path):
    chunks = _chunks(6)
    settings = _settings(tmp_path)

    first = _generator(settings)
    first.generate_cards_for_chunks(chunks[:4])

    second = _generator(settings)
    cards = second.generate_cards_for_chunks(chunks)

    assert {i for i, _ in second.calls} == {4, 5}, "only the unchecked chunks were regenerated"
    assert len(cards) == 6 * len(CardType)


def test_a_failed_card_type_is_retried_on_resume(tmp_path):
    chunks = _chunks(2)
    settings = _settings(tmp_path)

    first = _generator(settings, fail_for={chunks[0].chunk_id})
    cards_a = first.generate_cards_for_chunks(chunks)
    assert first.last_run_stats["failed_chunks"] == 1
    assert first.last_run_stats["failed_card_types"] == {ct.value: 1 for ct in CardType}
    # Only chunk 1's cards survived the run.
    assert len(cards_a) == len(CardType)

    second = _generator(settings)  # no failures this time
    cards_b = second.generate_cards_for_chunks(chunks)

    assert {i for i, _ in second.calls} == {0}, "the failed chunk must be re-attempted"
    assert len(cards_b) == 2 * len(CardType)
    assert second.last_run_stats["failed_card_types"] == {}


def test_resume_false_regenerates_everything(tmp_path):
    chunks = _chunks(3)
    settings = _settings(tmp_path)

    _generator(settings).generate_cards_for_chunks(chunks)

    second = _generator(settings)
    second.generate_cards_for_chunks(chunks, resume=False)

    assert len(second.calls) == 3 * len(CardType)
    assert second.last_run_stats["chunks_resumed"] == 0


def test_the_checkpoint_can_be_disabled(tmp_path):
    chunks = _chunks(2)
    settings = _settings(tmp_path, card_checkpoint_enabled=False)

    gen = _generator(settings)
    gen.generate_cards_for_chunks(chunks)
    assert gen.last_run_stats["checkpoint_path"] is None

    second = _generator(settings)
    second.generate_cards_for_chunks(chunks)
    assert len(second.calls) == 2 * len(CardType), "without a checkpoint nothing is resumed"


def test_stats_are_reported_even_when_the_generator_is_the_stub(tmp_path):
    """`generate_phase2_artifacts` reads `.last_run_stats` — the stub must have it too."""
    from src.pdf_ingestion.card_generator import StubLLM

    stub = StubLLM()
    cards = stub.generate_cards_for_chunks(_chunks(3))
    assert len(cards) == 3 * len(CardType)
    assert stub.last_run_stats["failed_card_types"] == {}
    assert stub.last_run_stats["cards"] == len(cards)
