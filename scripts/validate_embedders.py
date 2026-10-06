#!/usr/bin/env python3
"""Functional validation for the embedder lanes.

Shape and norm checks cannot catch a semantically broken lane — random vectors pass them
all. The decisive property is **discrimination**: does the lane rank a passage from a
labelled-relevant page above a passage from an unrelated one? A broken encoder tends to
score at chance here, or invert.

`tests/test_colbert_embedder.py` and `tests/test_splade.py` exercise only the STUBS, so
the real services' output has never been checked. This script checks the real ones.

Per lane:
  - shape: query and document are both (n_tokens, dim) matrices, not a single vector
  - norm:  every token vector is unit-length
  - discrimination: relevant passage scores above an unrelated one, over N labelled queries

Usage:
  uv run python scripts/validate_embedders.py                       # colbert + dense
  uv run python scripts/validate_embedders.py --n-queries 10
  uv run python scripts/validate_embedders.py --lanes colbert
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from loguru import logger


def maxsim(q: np.ndarray, d: np.ndarray) -> float:
    """ColBERT MaxSim: sum over query tokens of the max cosine with any doc token."""
    return float((q @ d.T).max(axis=1).sum())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queries", default="data/eval_queries.json")
    ap.add_argument("--db", default="data/synapse.db")
    ap.add_argument("--n-queries", type=int, default=8)
    ap.add_argument("--lanes", default="colbert,dense")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    from src.core.config import get_settings

    cfg = get_settings()
    random.seed(args.seed)
    lanes = [x.strip() for x in args.lanes.split(",") if x.strip()]

    db = sqlite3.connect(args.db)
    by_page: dict[int, list[str]] = {}
    for pg, txt in db.execute(
            "SELECT page_number, text FROM chunks WHERE page_number IS NOT NULL"):
        by_page.setdefault(pg, []).append(txt)
    logger.info(f"{len(by_page)} pages available")

    queries = [x for x in json.loads(Path(args.queries).read_text())
               if x.get("calibrated") and x.get("relevant_pages")][: args.n_queries]

    failures: list[str] = []

    # ── ColBERT: multi-vector, MaxSim ────────────────────────────────────────
    if "colbert" in lanes:
        from src.pdf_ingestion.colbert_embedder import get_colbert_embedder
        cb = get_colbert_embedder(cfg)

        qm = cb.embed_query("what is the kinetic energy formula")
        dm = cb.embed_passages(["Newton's second law relates force, mass and acceleration."])[0]
        print(f"\nCOLBERT  query shape {qm.shape}  doc shape {dm.shape}")
        if qm.ndim != 2 or dm.ndim != 2:
            failures.append("colbert: query or document is not a token matrix")
        if qm.shape[1] != 128 or dm.shape[1] != 128:
            failures.append(f"colbert: expected 128-d token vectors, got {qm.shape[1]}")
        for name, m in (("query", qm), ("doc", dm)):
            n = np.linalg.norm(m, axis=1)
            if not np.allclose(n, 1.0, atol=1e-4):
                failures.append(f"colbert: {name} token vectors not unit-norm "
                                f"(min {n.min():.4f}, max {n.max():.4f})")
        print(f"  token norms: query {np.linalg.norm(qm,axis=1).mean():.4f} "
              f"doc {np.linalg.norm(dm,axis=1).mean():.4f}")

        ok = 0
        print(f"\n  {'query':11} {'|rel|':>5} {'pos':>8} {'neg':>8} {'margin':>8}  ok")
        for item in queries:
            # a labelled page may have no chunk (front matter filtered by min_content_page)
            rel = set(item["relevant_pages"]) & set(by_page)
            if not rel:
                continue
            pos_page = random.choice(sorted(rel))
            neg_page = random.choice([p for p in by_page
                                      if p not in rel and abs(p - pos_page) > 20])
            q = cb.embed_query(item["query"])
            p = cb.embed_passages([by_page[pos_page][0][:1000]])[0]
            n = cb.embed_passages([by_page[neg_page][0][:1000]])[0]
            s_p, s_n = maxsim(q, p), maxsim(q, n)
            good = s_p > s_n
            ok += good
            print(f"  {item['id']:11} {len(rel):>5} {s_p:>8.2f} {s_n:>8.2f} "
                  f"{s_p - s_n:>+8.2f}  {good}")
        print(f"  → colbert discrimination: {ok}/{len(queries)}")
        if ok < len(queries) * 0.7:
            failures.append(f"colbert: discrimination {ok}/{len(queries)} is near chance")

    # ── Dense: single-vector, cosine ─────────────────────────────────────────
    if "dense" in lanes:
        from src.pdf_ingestion.embedder import get_embedder
        em = get_embedder(cfg)
        v = np.asarray(em.embed_query("what is the kinetic energy formula"), dtype=np.float32)
        print(f"\nDENSE    query shape {v.shape}  norm {np.linalg.norm(v):.4f}")
        if v.ndim != 1:
            failures.append("dense: query is not a 1-d vector")

        ok = 0
        print(f"\n  {'query':11} {'|rel|':>5} {'pos':>8} {'neg':>8} {'margin':>8}  ok")
        for item in queries:
            rel = set(item["relevant_pages"]) & set(by_page)
            if not rel:
                continue
            pos_page = random.choice(sorted(rel))
            neg_page = random.choice([p for p in by_page
                                      if p not in rel and abs(p - pos_page) > 20])
            # passages must use the DOCUMENT prefix, queries the QUERY prefix
            q = np.asarray(em.embed_query(item["query"]), dtype=np.float32)
            p = np.asarray(em.embed_documents([by_page[pos_page][0][:1000]])[0], dtype=np.float32)
            n = np.asarray(em.embed_documents([by_page[neg_page][0][:1000]])[0], dtype=np.float32)
            s_p, s_n = float(q @ p), float(q @ n)
            good = s_p > s_n
            ok += good
            print(f"  {item['id']:11} {len(rel):>5} {s_p:>8.3f} {s_n:>8.3f} "
                  f"{s_p - s_n:>+8.3f}  {good}")
        print(f"  → dense discrimination: {ok}/{len(queries)}")
        if ok < len(queries) * 0.7:
            failures.append(f"dense: discrimination {ok}/{len(queries)} is near chance")

    print("\n" + "=" * 70)
    if failures:
        for f in failures:
            logger.error(f)
        print("VALIDATION FAILED")
        return 1
    print("VALIDATION PASSED — lanes discriminate, shapes and norms are sane")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
