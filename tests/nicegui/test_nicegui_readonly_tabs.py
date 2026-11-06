"""NG-P3 — headless UI test for the read-only Status / Cards / RAPTOR tabs.

Proves the tabs BUILD and RENDER the loader output (the count-correctness of the loaders is the
separate acceptance harness `logs/p1/step10/ng_p3_acceptance.py`). The backend is faked at the
`DocumentStore` boundary the loaders import inside themselves, so no cluster or real DB is touched.

Run (the plugin, loaded globally, breaks unrelated tests — hence the opt-in guard):
    NICEGUI_UI_TESTS=1 .venv/bin/python -m pytest \
        -p nicegui.testing.user_plugin tests/nicegui/test_nicegui_readonly_tabs.py -q
"""
from __future__ import annotations

import os

import pytest

if os.environ.get("NICEGUI_UI_TESTS") != "1":
    pytest.skip(
        "NiceGUI UI test — run with NICEGUI_UI_TESTS=1 and -p nicegui.testing.user_plugin",
        allow_module_level=True,
    )

from datetime import datetime  # noqa: E402

from nicegui import ui  # noqa: E402

pytestmark = pytest.mark.nicegui_main_file("src/frontend/nicegui_app.py")

CHUNKS = 4242          # distinctive so the rendered total cannot collide with another number
N_VISUAL = 5
N_RAPTOR = 3           # 2 x L1 + 1 x L2


class _FakeDriver:
    def __init__(self, *_a, **_kw) -> None:
        pass

    def session(self):
        return _NoopSession()

    def close(self) -> None:
        pass


class _NoopSession:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def run(self, _cypher, **_kw):
        class _R:
            def single(self):
                class _C:
                    def __getitem__(self, _k):
                        return 0
                return _C()
        return _R()


class _Doc:
    id = "doc-0001"
    filename = "fake.pdf"
    tenant_id = "global"
    source_type = "base_textbook"
    page_count = 10
    chunk_count = CHUNKS
    embedding_version = "nomic"
    colpali_status = "ready"
    created_at = datetime(2026, 1, 1)


class _Card:
    def __init__(self, card_type: str, content: str) -> None:
        self.card_type = card_type
        self.title = card_type.title()
        self.content = content


class _Node:
    def __init__(self, level: int, cluster_id: int) -> None:
        self.level = level
        self.cluster_id = cluster_id
        self.summary = f"summary {cluster_id}"
        self.child_ids_json = "[1, 2]"
        self.version = 1


class _Store:
    def __init__(self, _cfg) -> None:
        pass

    def list_documents(self):
        return [_Doc()]

    def get_cards(self, _doc_id, card_type=None):
        if card_type == "definition":
            return [_Card("definition", f"definition {i}") for i in range(3)]
        if card_type == "summary":
            return [_Card("summary", "a summary")]
        return []

    def get_raptor_tree(self, _doc_id):
        return [_Node(1, 1), _Node(1, 2), _Node(2, 0)]

    def get_page_images(self, _doc_id):
        return list(range(N_VISUAL))


def _install_fake_store(monkeypatch: pytest.MonkeyPatch) -> None:
    import neo4j

    import src.pdf_ingestion.store as store_mod
    monkeypatch.setattr(store_mod, "DocumentStore", _Store)
    # The Graph tab (P4) builds here too and reads Memgraph — fake the driver so this test does
    # not depend on a running container.
    monkeypatch.setattr(
        neo4j, "GraphDatabase", type("G", (), {"driver": staticmethod(_FakeDriver)})
    )


async def test_readonly_tabs_build_and_render(user, monkeypatch):
    _install_fake_store(monkeypatch)
    await user.open("/")

    # The six tabs exist (Ask / Status / Cards / RAPTOR / Visual / Graph).
    assert len(user.find(ui.tab).elements) == 6

    # Status tab: the header metrics render the loader's totals (visible labels).
    await user.should_see("Total chunks", retries=50)
    await user.should_see(f"{CHUNKS:,}", retries=50)          # "4,242"
    await user.should_see("Visual pages", retries=50)
    await user.should_see("RAPTOR nodes", retries=50)

    # RAPTOR tab: the metric row renders.
    await user.should_see("Total nodes", retries=50)
    await user.should_see("Cluster summaries (L1)", retries=50)

    # Cards tab: the Material selector built (a doc with cards was found).
    assert len(user.find(ui.select).elements) >= 1
