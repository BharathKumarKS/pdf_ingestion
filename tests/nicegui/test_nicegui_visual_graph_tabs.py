"""NG-P4 — headless UI test for the Visual and Graph tabs.

Proves the two tabs BUILD and RENDER their loader output (the data correctness is the separate
acceptance harness `logs/p1/step10/ng_p4_acceptance.py`): the Graph tab shows the Memgraph metric
row, a visual query renders a `ui.image`, and a graph query renders its matched concepts. The
backend is faked at the module boundaries each loader imports inside itself — no cluster, no
Memgraph, no real images touched.

Run (opt-in; the plugin, loaded globally, breaks unrelated tests):
    NICEGUI_UI_TESTS=1 .venv/bin/python -m pytest \
        -p nicegui.testing.user_plugin tests/nicegui/test_nicegui_visual_graph_tabs.py -q
"""
from __future__ import annotations

import io
import os

import pytest

if os.environ.get("NICEGUI_UI_TESTS") != "1":
    pytest.skip(
        "NiceGUI UI test — run with NICEGUI_UI_TESTS=1 and -p nicegui.testing.user_plugin",
        allow_module_level=True,
    )

import numpy as np  # noqa: E402
from nicegui import ui  # noqa: E402
from PIL import Image  # noqa: E402

pytestmark = pytest.mark.nicegui_main_file("src/frontend/nicegui_app.py")

EDGES = 987654  # distinctive, so the rendered metric cannot collide with another number
GRAPH_COUNTS = {"Document": 2, "Chunk": 100, "Page": 50, "Concept": 7}


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, "PNG")
    return buf.getvalue()


class _FakeCount:
    def __init__(self, c: int) -> None:
        self._c = c

    def __getitem__(self, key: str) -> int:
        assert key == "c"
        return self._c


class _FakeResult:
    def __init__(self, c: int) -> None:
        self._c = c

    def single(self) -> _FakeCount:
        return _FakeCount(self._c)


class _FakeSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, cypher: str, **_kw) -> _FakeResult:
        if "-[r]->" in cypher:
            return _FakeResult(EDGES)
        for label, count in GRAPH_COUNTS.items():
            if f":{label}" in cypher:
                return _FakeResult(count)
        return _FakeResult(0)


class _FakeDriver:
    def __init__(self, *_a, **_kw) -> None:
        pass

    def session(self) -> _FakeSession:
        return _FakeSession()

    def close(self) -> None:
        pass


class _FakeEmb:
    def embed_query(self, _t: str) -> np.ndarray:
        return np.zeros(768, dtype=np.float32)

    def embed_query_text(self, _t: str) -> np.ndarray:
        return np.zeros((1, 128), dtype=np.float32)


class _FakeStore:
    def __init__(self, _cfg) -> None:
        pass

    # Status / Cards / RAPTOR tabs build too — keep them harmless.
    def list_documents(self):
        return []

    def get_cards(self, *_a, **_kw):
        return []

    def get_raptor_tree(self, *_a, **_kw):
        return []

    def get_page_images(self, *_a, **_kw):
        return []

    # Visual
    def count_visual_vectors(self, _tenants) -> int:
        return 5

    def visual_search(self, **_kw):
        return [{"page_number": 7, "score_cosine": 0.9, "document_id": "d1",
                 "image_key": "d1/page_0007.png"}]


class _FakeImageStore:
    def get(self, _key: str) -> bytes:
        return _png_bytes()


class _FakeGraphBuilder:
    def graph_search(self, **_kw):
        return [{"chunk_id": "c1", "text_preview": "a passage", "concept_path": ["gravity"],
                 "matched_concepts": 1}]


def _install_fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    import neo4j

    import src.pdf_ingestion.cluster_embedder as ce_mod
    import src.pdf_ingestion.colpali_embedder as cp_mod
    import src.pdf_ingestion.graph_builder as gb_mod
    import src.pdf_ingestion.image_store as is_mod
    import src.pdf_ingestion.store as store_mod

    monkeypatch.setattr(
        neo4j, "GraphDatabase", type("G", (), {"driver": staticmethod(_FakeDriver)})
    )
    monkeypatch.setattr(store_mod, "DocumentStore", _FakeStore)
    monkeypatch.setattr(cp_mod, "get_colpali_embedder", lambda cfg: _FakeEmb())
    monkeypatch.setattr(is_mod, "get_image_store", lambda cfg: _FakeImageStore())
    monkeypatch.setattr(ce_mod, "get_cluster_embedder", lambda cfg: _FakeEmb())
    monkeypatch.setattr(gb_mod, "get_graph_builder", lambda cfg: _FakeGraphBuilder())


async def test_visual_and_graph_tabs(user, monkeypatch):
    _install_fakes(monkeypatch)
    await user.open("/")

    assert len(user.find(ui.tab).elements) == 6

    # Graph tab: the Memgraph metric row renders the faked counts.
    await user.should_see("Edges", retries=50)
    await user.should_see(f"{EDGES:,}", retries=50)

    # Visual tab: a query renders a page image.
    user.find(marker="visual-input").type("a pendulum")
    user.find(marker="visual-button").click()
    await user.should_see(ui.image, retries=50)
    await user.should_see("Page 7  ·  cosine 0.9", retries=50)

    # Graph tab: a query renders its matched concepts.
    user.find(marker="graph-input").type("why does a satellite stay in orbit?")
    user.find(marker="graph-button").click()
    await user.should_see("🔗 1 concept(s) matched: gravity", retries=50)
