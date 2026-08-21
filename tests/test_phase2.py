"""Phase 2 test suite — card generator, RAPTOR tree, store, version control.
All unit tests use USE_STUB_LLM=true so no Ollama is needed.
Phase 1 tests are re-run at the end to confirm nothing regressed.
"""
from __future__ import annotations
import json, sys, uuid
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def p2_settings(tmp_path):
    from src.core.config import Settings
    return Settings(
        use_stub_embedder=True,
        use_stub_llm=True,
        qdrant_in_memory=True,
        sqlite_url=f"sqlite:///{tmp_path}/phase2.db",
    )


@pytest.fixture
def ingested_doc(p2_settings, tmp_path):
    """Phase 1 ingest of the sample PDF — foundation for Phase 2 tests."""
    from scripts.create_test_pdf import create_test_pdf
    from src.pdf_ingestion.store import ingest_pdf

    pdf = tmp_path / "physics.pdf"
    create_test_pdf(str(pdf))
    return ingest_pdf(
        pdf_path=str(pdf),
        tenant_id="global",
        source_type="base_textbook",
        is_global_baseline=True,
        settings=p2_settings,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Database schema — new tables exist alongside Phase 1 tables
# ═══════════════════════════════════════════════════════════════════════════

class TestDatabaseSchema:
    def test_all_tables_present(self, p2_settings):
        from src.core.database import get_engine
        from sqlmodel import inspect as sql_inspect
        engine    = get_engine(p2_settings)
        inspector = sql_inspect(engine)
        tables    = set(inspector.get_table_names())
        # Phase 1 tables intact
        assert "documents" in tables
        assert "chunks"    in tables
        # Phase 2 tables added
        assert "cards"       in tables
        assert "raptor_nodes" in tables

    def test_card_columns(self, p2_settings):
        from src.core.database import get_engine
        from sqlmodel import inspect as sql_inspect
        inspector = sql_inspect(get_engine(p2_settings))
        cols = {c["name"] for c in inspector.get_columns("cards")}
        for required in ("id", "chunk_id", "document_id", "tenant_id",
                         "card_type", "title", "content", "answer",
                         "version", "is_active"):
            assert required in cols, f"missing column: {required}"

    def test_raptor_node_columns(self, p2_settings):
        from src.core.database import get_engine
        from sqlmodel import inspect as sql_inspect
        inspector = sql_inspect(get_engine(p2_settings))
        cols = {c["name"] for c in inspector.get_columns("raptor_nodes")}
        for required in ("id", "document_id", "tenant_id", "level",
                         "parent_id", "cluster_id", "summary",
                         "child_ids_json", "qdrant_point_id",
                         "version", "is_active"):
            assert required in cols, f"missing column: {required}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Card generator (stub mode)
# ═══════════════════════════════════════════════════════════════════════════

class TestCardGenerator:
    def _make_chunk(self, idx: int = 0) -> "TextChunk":
        from src.pdf_ingestion.chunker import TextChunk
        return TextChunk(
            chunk_id=str(uuid.uuid4()),
            document_id="doc-1",
            tenant_id="global",
            chunk_index=idx,
            text="Newton's second law: force equals mass times acceleration.",
            char_start=0, char_end=60, token_count=10, page_number=1,
        )

    def test_stub_produces_8_cards(self, p2_settings):
        from src.pdf_ingestion.card_generator import get_card_generator
        gen   = get_card_generator(p2_settings)
        cards = gen.generate_cards_for_chunk(self._make_chunk())
        assert len(cards) == 8

    def test_all_card_types_present(self, p2_settings):
        from src.pdf_ingestion.card_generator import get_card_generator, ALL_CARD_TYPES
        gen   = get_card_generator(p2_settings)
        cards = gen.generate_cards_for_chunk(self._make_chunk())
        types = {c.card_type for c in cards}
        assert types == set(ALL_CARD_TYPES)

    def test_question_card_has_answer(self, p2_settings):
        from src.pdf_ingestion.card_generator import get_card_generator
        gen   = get_card_generator(p2_settings)
        cards = gen.generate_cards_for_chunk(self._make_chunk())
        q_cards = [c for c in cards if c.card_type == "question"]
        assert q_cards
        assert q_cards[0].answer is not None

    def test_non_question_cards_have_no_answer(self, p2_settings):
        from src.pdf_ingestion.card_generator import get_card_generator
        gen   = get_card_generator(p2_settings)
        cards = gen.generate_cards_for_chunk(self._make_chunk())
        non_q = [c for c in cards if c.card_type != "question"]
        for c in non_q:
            assert c.answer is None

    def test_cards_reference_correct_chunk(self, p2_settings):
        from src.pdf_ingestion.card_generator import get_card_generator
        chunk = self._make_chunk(idx=3)
        gen   = get_card_generator(p2_settings)
        cards = gen.generate_cards_for_chunk(chunk)
        for c in cards:
            assert c.chunk_id    == chunk.chunk_id
            assert c.document_id == chunk.document_id
            assert c.tenant_id   == chunk.tenant_id

    def test_batch_generation(self, p2_settings):
        from src.pdf_ingestion.card_generator import get_card_generator
        chunks = [self._make_chunk(i) for i in range(5)]
        gen    = get_card_generator(p2_settings)
        cards  = gen.generate_cards_for_chunks(chunks)
        assert len(cards) == 5 * 8  # 8 cards × 5 chunks


# ═══════════════════════════════════════════════════════════════════════════
# 3. Store — save and retrieve cards
# ═══════════════════════════════════════════════════════════════════════════

class TestCardStore:
    def test_save_and_retrieve_cards(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts, DocumentStore
        result = generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)

        store = DocumentStore(p2_settings)
        cards = store.get_cards(ingested_doc["document_id"])
        assert len(cards) > 0
        assert len(cards) == result["cards_generated"]

    def test_card_version_defaults_to_1(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts, DocumentStore
        generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        cards = DocumentStore(p2_settings).get_cards(ingested_doc["document_id"])
        assert all(c.version == 1 for c in cards)

    def test_cards_are_active_by_default(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts, DocumentStore
        generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        cards = DocumentStore(p2_settings).get_cards(ingested_doc["document_id"])
        assert all(c.is_active for c in cards)

    def test_filter_cards_by_type(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts, DocumentStore
        generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        store = DocumentStore(p2_settings)
        for ct in ("summary", "definition", "question", "formula"):
            typed = store.get_cards(ingested_doc["document_id"], card_type=ct)
            assert all(c.card_type == ct for c in typed)

    def test_get_cards_for_chunks(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts, DocumentStore
        generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        store = DocumentStore(p2_settings)
        all_cards = store.get_cards(ingested_doc["document_id"])
        chunk_ids = list({c.chunk_id for c in all_cards})[:2]

        # Returns cards matching those chunk_ids
        result = store.get_cards_for_chunks(chunk_ids)
        assert len(result) > 0
        assert all(c.chunk_id in chunk_ids for c in result)

        # card_types filter works
        defs = store.get_cards_for_chunks(chunk_ids, card_types=["definition"])
        assert all(c.card_type == "definition" for c in defs)

        # Empty chunk_ids returns empty list
        assert store.get_cards_for_chunks([]) == []


# ═══════════════════════════════════════════════════════════════════════════
# 4. RAPTOR tree
# ═══════════════════════════════════════════════════════════════════════════

class TestRaptorTree:
    def test_tree_nodes_produced(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts
        result = generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        assert result["raptor_nodes"] > 0
        assert len(result["raptor_levels"]) >= 1

    def test_nodes_stored_in_sqlite(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts, DocumentStore
        result = generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        nodes  = DocumentStore(p2_settings).get_raptor_tree(ingested_doc["document_id"])
        assert len(nodes) == result["raptor_nodes"]

    def test_raptor_nodes_have_version_control(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts, DocumentStore
        generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        nodes = DocumentStore(p2_settings).get_raptor_tree(ingested_doc["document_id"])
        assert all(n.version   == 1    for n in nodes)
        assert all(n.is_active == True for n in nodes)

    def test_raptor_nodes_upserted_to_qdrant(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts
        from src.core.database import get_qdrant
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        result = generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        client = get_qdrant(p2_settings)

        # Count RAPTOR points in Qdrant
        raptor_results = client.scroll(
            collection_name=p2_settings.qdrant_collection,
            scroll_filter=Filter(
                must=[FieldCondition(
                    key="source_type",
                    match=MatchValue(value="raptor_summary")
                )]
            ),
            limit=100,
            with_payload=True,
        )
        raptor_points = raptor_results[0]
        assert len(raptor_points) == result["raptor_nodes"]

    def test_raptor_payload_fields(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts
        from src.core.database import get_qdrant
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        client = get_qdrant(p2_settings)
        pts, _ = client.scroll(
            collection_name=p2_settings.qdrant_collection,
            scroll_filter=Filter(must=[
                FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))
            ]),
            limit=5,
            with_payload=True,
        )
        for pt in pts:
            p = pt.payload
            assert p["source_type"]    == "raptor_summary"
            assert p["tenant_id"]      == "global"
            assert "raptor_level"      in p
            assert "cluster_id"        in p
            assert p["text"]

    def test_child_ids_parseable(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts, DocumentStore
        generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        nodes = DocumentStore(p2_settings).get_raptor_tree(ingested_doc["document_id"])
        for n in nodes:
            child_ids = json.loads(n.child_ids_json)
            assert isinstance(child_ids, list)
            assert len(child_ids) > 0

    def test_level2_nodes_have_parent(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts, DocumentStore
        generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        nodes  = DocumentStore(p2_settings).get_raptor_tree(ingested_doc["document_id"])
        level2 = [n for n in nodes if n.level == 2]
        level1 = [n for n in nodes if n.level == 1]
        # If level-2 nodes exist, level-1 nodes must have a parent_id
        if level2:
            assert all(n.parent_id is not None for n in level1)


# ═══════════════════════════════════════════════════════════════════════════
# 5. Full Phase 2 orchestration
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase2Orchestration:
    def test_generate_artifacts_returns_summary(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts
        result = generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        assert result["document_id"]       == ingested_doc["document_id"]
        assert result["cards_generated"]   > 0
        assert result["raptor_nodes"]      > 0
        assert isinstance(result["raptor_levels"], list)

    def test_invalid_doc_raises(self, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts
        from src.core.database import get_engine  # ensure tables exist
        get_engine(p2_settings)
        with pytest.raises(ValueError, match="not found"):
            generate_phase2_artifacts("non-existent-id", p2_settings)

    def test_phase1_qdrant_points_intact_after_phase2(self, ingested_doc, p2_settings):
        """Phase 2 must not delete or overwrite Phase 1 chunk vectors."""
        from src.pdf_ingestion.store import generate_phase2_artifacts
        from src.core.database import get_qdrant
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        client = get_qdrant(p2_settings)

        chunk_pts, _ = client.scroll(
            collection_name=p2_settings.qdrant_collection,
            scroll_filter=Filter(must=[
                FieldCondition(key="source_type", match=MatchValue(value="base_textbook"))
            ]),
            limit=100,
            with_payload=True,
        )
        assert len(chunk_pts) == ingested_doc["chunk_count"]

    def test_cards_per_chunk_count(self, ingested_doc, p2_settings):
        """Every chunk must have exactly 8 cards (one per card type)."""
        from src.pdf_ingestion.store import generate_phase2_artifacts, DocumentStore
        generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        store = DocumentStore(p2_settings)
        cards = store.get_cards(ingested_doc["document_id"])
        assert len(cards) == ingested_doc["chunk_count"] * 8


# ═══════════════════════════════════════════════════════════════════════════
# 6. Phase 1 regression — confirm nothing broke
# ═══════════════════════════════════════════════════════════════════════════

class TestPhase1Regression:
    """Re-run critical Phase 1 paths to confirm Phase 2 changes didn't break them."""

    def test_ingest_pdf_still_works(self, p2_settings, tmp_path):
        from scripts.create_test_pdf import create_test_pdf
        from src.pdf_ingestion.store import ingest_pdf
        pdf = tmp_path / "regress.pdf"
        create_test_pdf(str(pdf))
        result = ingest_pdf(
            pdf_path=str(pdf),
            tenant_id="user_regress",
            source_type="user_upload",
            is_global_baseline=False,
            settings=p2_settings,
        )
        assert result["chunk_count"] > 0
        assert result["document_id"]

    def test_search_still_works_after_phase2(self, ingested_doc, p2_settings):
        from src.pdf_ingestion.store import generate_phase2_artifacts, DocumentStore
        from src.pdf_ingestion.embedder import get_embedder
        generate_phase2_artifacts(ingested_doc["document_id"], p2_settings)
        embedder = get_embedder(p2_settings)
        q_vec    = embedder.embed_query("Newton's law of motion")
        results  = DocumentStore(p2_settings).search(
            query_vector=q_vec,
            tenant_id="global",
            source_type="base_textbook",
        )
        assert len(results) > 0

    def test_new_tables_dont_shadow_old_ones(self, p2_settings):
        from src.core.database import get_engine
        from sqlmodel import inspect as sql_inspect
        inspector = sql_inspect(get_engine(p2_settings))
        tables    = set(inspector.get_table_names())
        # All Phase 1 tables still present
        assert {"documents", "chunks"}.issubset(tables)


# ═══════════════════════════════════════════════════════════════════════════
# 7. Ollama integration (real LLM — requires Ollama running)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.slow
@pytest.mark.integration
class TestOllamaCardGeneration:
    def test_real_llama_generates_valid_cards(self, tmp_path):
        from src.core.config import Settings
        from src.pdf_ingestion.chunker import TextChunk
        from src.pdf_ingestion.card_generator import OllamaCardGenerator, ALL_CARD_TYPES

        cfg = Settings(use_stub_llm=False, use_stub_embedder=True,
                       qdrant_in_memory=True, sqlite_url=f"sqlite:///{tmp_path}/llm.db")
        chunk = TextChunk(
            chunk_id=str(uuid.uuid4()), document_id="d1", tenant_id="global",
            chunk_index=0,
            text=(
                "Newton's second law states that the acceleration of an object "
                "is directly proportional to the net force and inversely "
                "proportional to its mass: F = ma."
            ),
            char_start=0, char_end=150, token_count=30, page_number=1,
        )
        gen   = OllamaCardGenerator(settings=cfg)
        cards = gen.generate_cards_for_chunk(chunk)

        # Card count is variable — nullable types (definition, example, etc.)
        # return 0 cards when not applicable; question/factoid return multiple.
        assert len(cards) >= 1
        types = {c.card_type for c in cards}
        assert types.issubset(set(ALL_CARD_TYPES))

        for c in cards:
            assert c.title.strip(),   f"{c.card_type}: empty title"
            assert c.content.strip(), f"{c.card_type}: empty content"

        q_cards = [c for c in cards if c.card_type == "question"]
        assert q_cards[0].answer and q_cards[0].answer.strip()

        print(f"\n[Ollama] Generated {len(cards)} cards")
        for c in cards:
            print(f"  [{c.card_type:15s}] {c.title}: {c.content[:60]}…")
