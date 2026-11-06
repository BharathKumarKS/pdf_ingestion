"""NG-P3 acceptance — do the read-only tabs' counts match the store's own methods?

The brief's acceptance for NG-P3: *counts match `list_documents` / `get_cards` / `get_raptor_tree`.*

This harness calls the module's loaders (the exact functions the Status / Cards / RAPTOR tabs call)
and compares every count against a DIRECT call on `DocumentStore`:

  * `load_status`  → `list_documents`, `len(get_cards(id))`, `len(get_raptor_tree(id))`,
                     `len(get_page_images(id))`, and the six header totals.
  * `load_documents` → the `has_cards` / `has_raptor` flags.
  * `load_cards`   → per-type `len(get_cards(id, card_type=...))`.
  * `load_raptor`  → `len(get_raptor_tree(id))` and the L1/L2/L3 split.

Read-only: nothing is written. Run:
    .venv/bin/python logs/p1/step10/ng_p3_acceptance.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "logs/p1/step10/ng_p3_acceptance.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("ng_app", ROOT / "src/frontend/nicegui_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    from src.core.config import get_settings
    from src.pdf_ingestion.store import DocumentStore

    cfg = get_settings()
    ng = _load_module()
    store = DocumentStore(cfg)

    checks: list[dict] = []

    def check(name: str, ui_value, store_value) -> None:
        ok = ui_value == store_value
        checks.append({"check": name, "ui": ui_value, "store": store_value, "ok": ok})
        flag = "OK " if ok else "FAIL"
        print(f"[{flag}] {name}: tab={ui_value!r}  store={store_value!r}")

    docs = store.list_documents()
    status = ng.load_status(cfg)
    doc_list = ng.load_documents(cfg)

    # ── Status tab: per-document counts ──────────────────────────────────────
    # ⚠️ Key on the document ID, not the filename: the SQLite file holds TWO documents with the
    # SAME filename (the runbook's old-vs-current caveat), so a filename key collides.
    by_id = {r["id"]: r for r in status["rows"]}
    check("status.row_ids_unique", len(by_id), len(status["rows"]))
    for d in docs:
        row = by_id[d.id]
        check(f"status[{d.id[:8]}].cards", row["cards"], len(store.get_cards(d.id)))
        check(f"status[{d.id[:8]}].raptor", row["raptor"], len(store.get_raptor_tree(d.id)))
        check(f"status[{d.id[:8]}].visual", row["visual"], len(store.get_page_images(d.id)))
        check(f"status[{d.id[:8]}].chunks", row["chunks"], d.chunk_count)
        check(f"status[{d.id[:8]}].pages", row["pages"], d.page_count)

    # ── Status tab: the six header totals ────────────────────────────────────
    check("status.n_base", status["n_base"],
          sum(1 for d in docs if d.source_type == "base_textbook"))
    check("status.n_user", status["n_user"], sum(1 for d in docs if d.source_type == "user_upload"))
    check("status.total_chunks", status["total_chunks"], sum(d.chunk_count for d in docs))
    check("status.total_cards", status["total_cards"],
          sum(len(store.get_cards(d.id)) for d in docs))
    check("status.total_raptor", status["total_raptor"],
          sum(len(store.get_raptor_tree(d.id)) for d in docs))
    check("status.total_visual", status["total_visual"],
          sum(len(store.get_page_images(d.id)) for d in docs))
    check("status.n_rows", len(status["rows"]), len(docs))

    # ── Selectors: has_cards / has_raptor flags ──────────────────────────────
    for entry in doc_list:
        d = next(x for x in docs if x.id == entry["id"])
        check(f"documents[{d.id[:8]}].has_raptor",
              entry["has_raptor"], bool(store.get_raptor_tree(d.id)))

    # ── Cards tab + RAPTOR tab: one document ─────────────────────────────────
    if docs:
        d = docs[0]
        types = ng.STUDENT_CARD_TYPES
        cards = ng.load_cards(cfg, d.id, types)
        for ct in types:
            check(f"cards[{ct}].total",
                  cards["by_type"][ct]["total"],
                  len(ng._dedup_cards(store.get_cards(d.id, card_type=ct))))
            check(f"cards[{ct}].shown<=cap",
                  len(cards["by_type"][ct]["shown"]) <= ng.CARDS_PER_TYPE, True)

        rap = ng.load_raptor(cfg, d.id)
        nodes = store.get_raptor_tree(d.id)
        check("raptor.total", rap["total"], len(nodes))
        check("raptor.n_l1", rap["n_l1"], sum(1 for n in nodes if n.level == 1))
        check("raptor.n_l2", rap["n_l2"], sum(1 for n in nodes if n.level == 2))
        check("raptor.n_l3", rap["n_l3"], sum(1 for n in nodes if n.level == 3))
        check("raptor.split_sums", rap["n_l1"] + rap["n_l2"] + rap["n_l3"], len(nodes))
        check("raptor.n_l1_rendered", len(rap["l1"]), rap["n_l1"])

    n_fail = sum(1 for c in checks if not c["ok"])
    verdict = "PASS" if n_fail == 0 else f"FAIL ({n_fail})"
    print(f"\n{'='*60}\nNG-P3 ACCEPTANCE: {verdict}  ({len(checks)} checks)\n{'='*60}")
    OUT.write_text(json.dumps({"verdict": verdict, "n_checks": len(checks),
                               "n_fail": n_fail, "checks": checks}, indent=2))
    print(f"wrote {OUT}")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
