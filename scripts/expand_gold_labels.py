#!/usr/bin/env python3
"""Widen each gold question's relevant_pages to EVERY page that answers it.

The generator labels a question with the one page it came from, but a question generated
from p252 is usually also answerable from p95/p270. One-page labels understate recall: we
would be measuring the labeller, not the retriever.

Reuses the two-pass scan in validate_eval_calibration.py (stride 15, then ±8 dense), which
now runs over a thread pool with a disk verdict cache (Task 4a) — so this is resumable and
a re-run is bit-identical.

Usage:
    uv run python scripts/expand_gold_labels.py \\
        --query-file data/eval_queries_gold.json \\
        --pdf data/base_textbooks/feynman-lectures-on-physics-volume1.pdf \\
        --output data/eval_queries_gold_expanded.json

    # Probe two queries first — never run the whole set blind
    uv run python scripts/expand_gold_labels.py --limit 2 --output /tmp/expand_probe.json

    # Wiring check only: no judge calls, no output written
    uv run python scripts/expand_gold_labels.py --dry-run
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

_ROOT = Path(__file__).resolve().parents[1]


def load_scanner():
    """Import validate_eval_calibration.py (it is a script, not a module)."""
    path = _ROOT / "scripts" / "validate_eval_calibration.py"
    spec = importlib.util.spec_from_file_location("vec_under_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load scanner from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    p = argparse.ArgumentParser(
        description="Widen each gold question's relevant_pages to every page that answers it")
    p.add_argument("--query-file", default="data/eval_queries_gold.json")
    p.add_argument("--pdf", default="data/base_textbooks/feynman-lectures-on-physics-volume1.pdf")
    p.add_argument("--output", default="data/eval_queries_gold_expanded.json")
    p.add_argument("--limit", type=int, default=0, help="0 = all")
    p.add_argument("--dry-run", action="store_true",
                   help="Load and estimate the scan; no judge calls, no output written")
    vec = load_scanner()
    vec.add_scan_args(p)
    vec.add_judge_args(p)
    args = p.parse_args()

    queries = json.loads(Path(args.query_file).read_text())
    queries = [q for q in queries if not q.get("id", "").startswith("_")]
    if args.limit:
        queries = queries[: args.limit]

    store = vec._get_page_store(args.pdf, args)
    coarse = len(range(max(args.page_start, 1), min(args.page_end, store.n_pages) + 1, args.scan_stride))

    if args.dry_run:
        print(f"DRY RUN — no judge calls, no output written")
        print(f"  queries: {len(queries)}  (pdf: {store.n_pages} pages)")
        print(f"  per query: {coarse} coarse pages + a data-dependent dense pass (±{args.scan_window})")
        print(f"  coarse judge calls for this run: ~{len(queries) * coarse}")
        for q in queries:
            print(f"  {q['id']}: pages {sorted(q.get('relevant_pages') or [])} — {q['query'][:60]}")
        return 0

    vec.resolve_judge(args)

    out = []
    expanded = zero = 0
    for i, q in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {q['id']}: {q['query'][:60]}")
        before = set(q.get("relevant_pages") or [])
        try:
            hits = vec.scan_query(q, args.pdf, args)
            found = {h["page"] for h in hits if h["verdict"] == "YES"}
        except Exception as exc:
            print(f"    scan FAILED: {exc} — keeping original labels")
            out.append(q)
            continue
        after = sorted(before | found)
        gain = len(after) - len(before)
        expanded += 1
        if gain == 0:
            zero += 1
        print(f"    pages {sorted(before)} -> {after}  (+{gain})")
        q = dict(q)
        q["relevant_pages"] = after
        # 3c: a scan that found nothing is not a calibration — leave the entry
        # uncalibrated so it cannot pass the v2 schema test by accident.
        q["calibrated"] = bool(after)
        if not after:
            print(f"    WARNING: {q['id']} has no pages after the scan — left uncalibrated")
        q["calibration_note"] = (
            (q.get("calibration_note") or "") +
            f" | scan-expanded: {len(after)} pages"
        )
        out.append(q)

    Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nwrote {args.output}")
    print(f"expanded {expanded}/{len(queries)} queries; {zero} showed (+0)")

    cache = vec._get_verdict_cache(args)
    if cache is not None:
        print(f"verdict cache: {cache.hits} hits / {cache.misses} misses -> {cache.path}")
    else:
        print("verdict cache: disabled (--no-cache)")
    if queries and zero == len(queries):
        print("\n!! EVERY query showed (+0) — the scan is not finding anything. "
              "Stop and debug before using this output.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
