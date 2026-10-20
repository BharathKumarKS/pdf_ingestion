#!/usr/bin/env python3
"""Phase B (Step 9) — before-snapshot and scope probe. Read-only.

Answers, BEFORE any LLM is spent:

  1. **The card denominator.** `generate_phase2_artifacts` builds cards only for chunks where
     `content_filter.is_content(text)` — so it is fewer than the 3,796 chunks in the document.
     Measure it, do not assume it (the Step 9 plan says so explicitly).
  2. **The reranker-window tail.** §H records "57 of 5,048 chunks exceed the reranker's 512-token
     window (max 1,701) and are silently truncated". E1/E2 changed the chunking, so that number is
     new information — and a large tail directly caps §2's reranker ceiling.
  3. **The invariant Phase B is about to break.** `knowledge_base_v2` currently holds exactly the
     3,796 chunk points (Step 8's `verify_collection.py` exit 0). Phase 2 adds RAPTOR summaries to
     the SAME collection, so points != SQLite chunks afterwards. Record the "before".
  4. **Concurrency actually in force.** `card_gen_workers` defaults to 4 in `config.py` but `.env`
     sets 8 — the exact trap that made Step 8 attempt 3 run at the wrong worker count. And the real
     concurrency is `card_gen_workers × len(CardType)`, because each chunk runs its 8 card types in
     a nested pool.

Writes logs/p1/step10/phaseb_before.json. Exit 0 = the probe ran.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "logs/p1/step10/phaseb_before.json"
DB = ROOT / "data/synapse.db"
DOC_NEW = "7ba61432-c5e0-416d-aecf-25a232523481"
DOC_OLD = "6d55c52b-47ae-45ff-bee0-a3ca01ac93ce"
RERANKER_WINDOW_TOKENS = 512


def main() -> int:
    from src.core.config import get_settings
    from src.pdf_ingestion.card_generator import CardType
    from src.pdf_ingestion.content_filter import is_content

    cfg = get_settings()
    print("=" * 92)
    print("Phase B — before-snapshot and scope probe")
    print("=" * 92)

    print("\n[1] resolved settings (assert what is actually in force)")
    print(f"      qdrant_collection : {cfg.qdrant_collection}")
    print(f"      qdrant            : {cfg.qdrant_host or cfg.qdrant_url or cfg.qdrant_local_path}")
    print(f"      card_gen_workers  : {cfg.card_gen_workers}   "
          f"(config default is 4 — .env may override)")
    print(f"      card types        : {len(CardType)} -> {[t.value for t in CardType]}")
    print(f"      raptor_max_levels : {cfg.raptor_max_levels}   "
          f"raptor_min_cluster_size: {cfg.raptor_min_cluster_size}")
    print(f"      dense lane        : {cfg.dense_model} ({cfg.dense_dim}d)")
    print(f"      stubs e/l/g       : {cfg.use_stub_embedder} / {cfg.use_stub_llm} / "
          f"{cfg.use_stub_graph}")
    nested = cfg.card_gen_workers * len(CardType)
    print(f"      ⚠ effective LLM concurrency = card_gen_workers × |CardType| = "
          f"{cfg.card_gen_workers} × {len(CardType)} = {nested}")

    con = sqlite3.connect(DB)
    rows = con.execute(
        "SELECT chunk_index, text, token_count, page_number FROM chunks "
        "WHERE document_id = ? ORDER BY chunk_index", (DOC_NEW,)
    ).fetchall()
    # ``save_cards`` / ``save_raptor_tree`` DEACTIVATE the previous generation rather than
    # deleting it, so the table grows monotonically — count only ACTIVE rows or the "before"
    # baseline is inflated by history (the old doc shows 82,164 card rows, ~2 generations).
    cards_by_doc = dict(con.execute(
        "SELECT document_id, count(*) FROM cards WHERE is_active = 1 "
        "GROUP BY document_id").fetchall())
    cards_all_by_doc = dict(con.execute(
        "SELECT document_id, count(*) FROM cards GROUP BY document_id").fetchall())
    raptor_by_doc = dict(con.execute(
        "SELECT document_id, count(*) FROM raptor_nodes WHERE is_active = 1 "
        "GROUP BY document_id").fetchall())
    con.close()

    print(f"\n[2] card denominator — the E5 content filter (doc {DOC_NEW[:8]}…)")
    content, skipped = [], []
    for idx, text, tok, page in rows:
        (content if is_content(text) else skipped).append((idx, text, tok, page))
    print(f"      chunks total      : {len(rows)}")
    print(f"      content (cards)   : {len(content)}")
    print(f"      skipped non-chapt : {len(skipped)}  "
          f"({100.0 * len(skipped) / max(len(rows), 1):.1f}%)")
    print(f"      => LLM calls ≈ content × {len(CardType)} = "
          f"{len(content) * len(CardType):,}")
    if skipped:
        pages = sorted({p for _, _, _, p in skipped if p is not None})
        print(f"      skipped pages span: {pages[:6]}{' …' if len(pages) > 6 else ''} "
              f"(n={len(pages)})")

    print(f"\n[3] reranker-window tail (§H, re-measured on v2)")
    toks = [t for _, _, t, _ in rows if t]
    over = [t for t in toks if t > RERANKER_WINDOW_TOKENS]
    print(f"      chunks with token_count: {len(toks)}")
    if toks:
        print(f"      > {RERANKER_WINDOW_TOKENS} tokens : {len(over)} "
              f"({100.0 * len(over) / len(toks):.2f}%)   max={max(toks)}  "
              f"median={sorted(toks)[len(toks) // 2]}")
    print(f"      §H's recorded old-index figure: 57 of 5,048 (1.13%), max 1,701")

    print(f"\n[4] the invariant Phase B breaks")
    print(f"      SQLite chunks for this doc : {len(rows)}")
    print(f"      ACTIVE cards for this doc  : {cards_by_doc.get(DOC_NEW, 0)} "
          f"(all rows incl. inactive: {cards_all_by_doc.get(DOC_NEW, 0)})")
    print(f"      ACTIVE RAPTOR nodes        : {raptor_by_doc.get(DOC_NEW, 0)}")
    others = {k: v for k, v in cards_all_by_doc.items() if k != DOC_NEW}
    for k, v in others.items():
        print(f"      [other doc {k[:8]}…] card rows={v}  "
              f"active={cards_by_doc.get(k, 0)}  raptor_active={raptor_by_doc.get(k, 0)}")
        print(f"        → {v} rows / {cards_by_doc.get(k, 0)} active = "
              f"{v / max(cards_by_doc.get(k, 0), 1):.2f} generations of history")

    # ── Qdrant: the collection Phase B mutates ───────────────────────────────
    qdrant_snapshot: dict = {}
    print(f"\n[5] Qdrant '{cfg.qdrant_collection}' — the collection Phase B MUTATES")
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        kwargs: dict = {"timeout": 60}
        if cfg.qdrant_url:
            kwargs.update(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key or None)
        elif cfg.qdrant_host:
            kwargs.update(host=cfg.qdrant_host, port=cfg.qdrant_port)
        else:
            kwargs.update(path=cfg.qdrant_local_path)
        qc = QdrantClient(**kwargs)
        info = qc.get_collection(cfg.qdrant_collection)
        n_raptor = int(qc.count(cfg.qdrant_collection, count_filter=Filter(must=[
            FieldCondition(key="source_type", match=MatchValue(value="raptor_summary"))]
        )).count or 0)
        qdrant_snapshot = {
            "collection": cfg.qdrant_collection,
            "host": cfg.qdrant_host or cfg.qdrant_url or cfg.qdrant_local_path,
            "points": int(info.points_count or 0),
            "vectors": list((info.config.params.vectors or {}).keys()),
            "raptor_summary_points": n_raptor,
        }
        print(f"      points now        : {qdrant_snapshot['points']}")
        print(f"      vectors           : {qdrant_snapshot['vectors']}")
        print(f"      source_type=raptor_summary : {n_raptor}")
        print(f"      chunk points      : {qdrant_snapshot['points'] - n_raptor}")
        qc.close()
    except Exception as exc:
        print(f"      !! could not read Qdrant: {type(exc).__name__}: {exc}")
        print("      (run with QDRANT_HOST / QDRANT_COLLECTION exported)")

    OUT.write_text(json.dumps({
        "document_id": DOC_NEW,
        "settings": {
            "qdrant_collection": cfg.qdrant_collection,
            "card_gen_workers": cfg.card_gen_workers,
            "card_types": [t.value for t in CardType],
            "effective_llm_concurrency": nested,
            "raptor_max_levels": cfg.raptor_max_levels,
            "raptor_min_cluster_size": cfg.raptor_min_cluster_size,
        },
        "chunks_total": len(rows),
        "chunks_content": len(content),
        "chunks_skipped_non_chapter": len(skipped),
        "estimated_llm_calls": len(content) * len(CardType),
        "token_window": {
            "window": RERANKER_WINDOW_TOKENS,
            "with_token_count": len(toks),
            "over_window": len(over),
            "max": max(toks) if toks else None,
            "median": sorted(toks)[len(toks) // 2] if toks else None,
        },
        "cards_existing": cards_by_doc.get(DOC_NEW, 0),
        "raptor_nodes_existing": raptor_by_doc.get(DOC_NEW, 0),
        # the OLD document's active cards — what B4's "untouched" check compares against
        "old_doc_active_cards": cards_by_doc.get(DOC_OLD, 0),
        # the "before" B5's invariant check compares against
        "qdrant_points": qdrant_snapshot.get("points"),
        "qdrant_snapshot": qdrant_snapshot,
    }, indent=2))
    print(f"\n  wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
