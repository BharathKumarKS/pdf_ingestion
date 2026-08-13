"""Pytest fixtures shared across all Phase 1 tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ── Make src importable ────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Force stub embedder + in-memory Qdrant for all tests unless overridden
os.environ.setdefault("USE_STUB_EMBEDDER", "true")
os.environ.setdefault("USE_STUB_LLM",      "true")
os.environ.setdefault("USE_STUB_COLPALI",  "true")
os.environ.setdefault("USE_STUB_GRAPH",    "true")
os.environ.setdefault("USE_STUB_SPLADE",   "true")
os.environ.setdefault("QDRANT_IN_MEMORY",  "true")
os.environ.setdefault("SQLITE_URL", "sqlite:///./data/test_synapse.db")


@pytest.fixture(autouse=True)
def reset_db_singletons():
    """Tear down cached DB clients between tests to avoid state leakage."""
    from src.core.database import reset_singletons
    from src.pdf_ingestion.graph_builder import reset_graph_builder
    from src.core.intent_router import reset_intent_router
    from src.pdf_ingestion.splade_embedder import reset_splade_embedder
    reset_singletons()
    reset_graph_builder()
    reset_intent_router()
    reset_splade_embedder()
    yield
    reset_singletons()
    reset_graph_builder()
    reset_intent_router()
    reset_splade_embedder()


@pytest.fixture(scope="session")
def sample_pdf(tmp_path_factory) -> Path:
    """Create a sample physics PDF once per test session."""
    out_dir = tmp_path_factory.mktemp("pdfs")
    out_path = out_dir / "sample_physics.pdf"

    # Import and call create_test_pdf
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts.create_test_pdf import create_test_pdf
    create_test_pdf(str(out_path))
    return out_path


@pytest.fixture
def settings():
    from src.core.config import Settings
    return Settings(
        use_stub_embedder=True,
        use_stub_llm=True,
        use_stub_colpali=True,
        use_stub_graph=True,
        qdrant_in_memory=True,
        sqlite_url="sqlite:///./data/test_synapse.db",
        debug=False,
    )
