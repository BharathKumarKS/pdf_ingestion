#!/usr/bin/env python
"""§I71 — does the §I39 content filter move base-lane PAGE RANKING?

Pre-registration (the spec, committed alone as `aa4b55b`, BEFORE this file existed):
`.hermes/plans/2026-10-24-p1-chunking-filter-ab-preregistration.md`.

⚠️ **If any number in the pre-registration is edited after this run starts, the run is VOID.**

What this is
------------
Arm 1 of the chunking question. The filter changes **which chunks are in the candidate pool** —
it changes no chunk's text, no chunk's id and no stored vector. So it is measurable **over the
vectors already in `knowledge_base_v2`**, with **no parse, no re-chunk and no re-embed of the
corpus**: the pool filter is the only variable.

    arm C (control)    the shipped filter: `is_content is not False` + inside the content window
                       (the pool §I70 used — 3,489 chunks)
    arm T (treatment)  `C` MINUS every chunk the CURRENT `content_filter.is_content()` rejects

⚠️ **The treatment is computed from the TEXT, not from the stored `is_content`** (pre-reg F1: the
stored column is STALE — it is written at ingest and the §I39 extension landed after both ingests;
reading it would silently produce a 5-chunk treatment and a near-null). Guard C4 asserts the
text-derived count, not the stored 5.

⚠️ **THE FIRST RUN (2026-10-24, session 15) WAS VOID ON C2/C4, AND THE PRE-REGISTRATION'S F1/F2
PREMISES WERE WRONG — measured, not inferred** (`chunk_filter_ab_firstrun_VOID.json`, sha256
`0b25fd34…`; re-registration `.hermes/plans/2026-10-24-p1-chunk-filter-ab-reregistration.md`).
The pre-registration's "263 (6.9 %)" is the **WHOLE-CORPUS** count over all 3,796 chunks. This
arm's pool is the **content window only** (pages 30–936 ⇒ 3,489 chunks), and **244 of the 263
rejects sit OUTSIDE that window**: the index is pages **937–968** (186, all above the window's 936),
front matter pages **2–14** (5, all below its 30), and the TOC pages **22–34** (72, of which only
the **19** chunks on pages 30–34 are in-window). So the treatment is **19 chunks, not 263** — the
window bounds already exclude 93 % of what the filter would have removed. That is the arm's real
headline, and it is why the re-registration restates C2/C4 in terms of the pool.
The pre-registration's F2 "pages with chunks 933" is also wrong: §I70's own artifact and this run
both measure **888** (guard X1: the Qdrant pool's pages and §I58's `reachable_pages()` agree exactly).

⚠️ **The ceiling moves with the pool, and that is part of the result.** §I58's reachable set is
"a page with >=1 chunk, `is_content is not False`, inside the window". Removing the flagged chunks
(19 of them, in-pool) can drop a page from the ceiling entirely, so each arm is normalised against
**its own** reachable set and
both are reported. Never silently re-normalise one arm against the other's ceiling.

⚠️ **A negative is interpretable** (pre-reg §2): a page scores at its single best chunk's rank, so
removing a high-ranking TOC/index chunk from page p can LOWER page p's score. The filter can improve
chunk-level precision while hurting page-level recall. This arm measures the page-level effect,
which is the one the gold set labels.

Embedders
---------
    PRIMARY    gemma@768   `google/embeddinggemma-300m` — the corpus + embedder we would ship, and
                           the §I70 winner. Documents get `title: none | text: `, queries get
                           `task: search result | query: ` (asymmetric; §I62's prefix trap).
    SECONDARY  qwen3@1024  the incumbent — FREE (the stored `dense_1024` vectors). Tests whether
                           the filter's effect is embedder-specific.
⚠️ Report both. The primary is NOT switched after seeing numbers (pre-reg §2).

Endpoint and rule (pre-reg §3, fixed before the run)
----------------------------------------------------
* Endpoint: **paired, ceiling-normalised R@20, arm T − arm C, n = 133**, under gemma@768.
* **Attributable iff the 95 % CI excludes 0.** Otherwise the honest statement is "applying the
  content filter does not move base-lane page ranking on this corpus" — a RESULT, not an
  unresolved one.
* ONE run. No extension. No arm added after seeing numbers.
* Reported alongside, always: raw R@20, R@100, pages covered per arm, chunks/page, the qwen3@1024
  secondary row, and ⚠️ `chunks/page` itself — page-deduped recall scores a page at its best
  chunk's rank, and §I70 measured 6.68 (old corpus) vs 4.07 (new): a 64 % difference in chances.

Guards (pre-reg §4 — each must be able to FAIL)
-----------------------------------------------
  C1  arm C reproduces §I70's qwen3@1024 row EXACTLY — R@20 0.293934 · R@100 0.569074 ·
      R@500 0.922982 · R@1000 1.0. The control pool is unchanged, so the instrument must be the
      same one that produced the register.
  C2  the treatment pool is EXACTLY `C` minus the flagged chunks; the IN-POOL flagged set is **19**
      (band: 19 TOC) and the WHOLE-CORPUS flagged set is **263** = §I39's 72 TOC / 186 index /
      5 front matter, of which **244 are out of window**. (C2′, restated in the re-registration:
      the first run's C2 asserted 263 against the pool, which is a category error.)
  C3  A-vs-A negative control: arm C is byte-identical when the corpus is re-embedded at a
      different batch size (an identical-by-construction comparison would be the §I63 "check that
      cannot fail" trap — the control re-embeds, so a nondeterministic endpoint CAN move it).
  C4  the treatment was built from the TEXT, not the stored `is_content` — assert 19, not 5.
  C5  every query whose reachable set is empty in an arm is reported, never silently dropped.
  C6  identical chunk→page mapping across arms (one shared `pages` array; a sha256 of it).
  X1  (extra, not a registered guard) the pool's page coverage equals §I58's `reachable_pages()` —
      the Qdrant pool and the SQLite ceiling must describe the same page set.
  X2  (extra) the resolved config names the remote store, not the local fallback (§I49 Finding 1).

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python -u logs/p1/step10/chunk_filter_ab.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.content_filter import (  # noqa: E402
    NON_CHAPTER_MARKERS,
    is_content,
    is_index_density,
    is_index_heading,
    is_index_layout,
    is_toc_layout,
)
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = REPO / "data/eval_queries_v2.json"
OUT = REPO / "logs/p1/step10/chunk_filter_ab.json"

NEW_DOC = "7ba61432"
COLLECTION = "knowledge_base_v2"
DENSE_VEC = "dense_1024"

EMBED_URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"

KS = (20, 100, 500, 1000)

# The one candidate this arm needs (pre-reg §2: gemma@768 primary).
GEMMA_HF = "google/embeddinggemma-300m"
GEMMA_DOC_PREFIX = "title: none | text: "
GEMMA_QRY_PREFIX = "task: search result | query: "

# §I39's independently measured band split for this corpus — C2 must reproduce it on the CORPUS.
I39_BANDS = {"toc": 72, "index": 186, "front_matter": 5}
# §I70's qwen3@1024 row, ceiling-normalised, every-chunk pool — C1 must reproduce it EXACTLY.
I70_QWEN3_1024 = {"R@20": 0.293934, "R@100": 0.569074, "R@500": 0.922982, "R@1000": 1.0}

# ── the measured pool/corpus constants (re-registration §2; NOT the pre-registration's 263-in-pool)
EXPECTED_POOL = 3489                 # in-window chunks (§I70's pool) — reproduces
EXPECTED_REACHABLE_PAGES = 888       # §I58 reachable pages (§I70's artifact says 888; the pre-reg
#                                      F2 table says 933 — that figure is wrong, guard X1 settles it)
EXPECTED_CORPUS_CHUNKS = 3796
EXPECTED_CORPUS_FLAGGED = 263        # §I39: 72 toc + 186 index + 5 front matter, over the CORPUS
EXPECTED_CORPUS_FLAGGED_OUT_OF_WINDOW = 244
EXPECTED_IN_POOL_FLAGGED = 19        # the treatment's REAL size: the 263 minus the 244 out of window
EXPECTED_STORED_FALSE = 5            # the stale stored column, which must NOT be what the arm uses


# ── cluster HTTP (verbatim from `embedder_screen.py`, which took it from §I63) ────────────────

def cluster_embed(texts: list[str], batch: int, model: str) -> np.ndarray:
    """Pooled vectors from the cluster, L2-normalised. Batched; honours the response `index`."""
    out: list[np.ndarray] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        body = json.dumps({"model": model, "input": chunk}).encode()
        req = urllib.request.Request(EMBED_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.load(r)
        items = sorted(d["data"], key=lambda x: x.get("index", 0))
        for it in items:
            out.append(np.asarray(it["embedding"], dtype=np.float64))
    m = np.asarray(out, dtype=np.float64)
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)


# ── reads (verbatim from `embedder_screen.py` == §I63) ────────────────────────────────────────

def scroll_pool(client, cfg) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Every in-window chunk: (full-dim vector, page_number, text) — filter == `store.py:336-369`."""
    vectors: list[list[float]] = []
    pages: list[int] = []
    texts: list[str] = []
    offset = None
    while True:
        pts, offset = client.scroll(
            collection_name=COLLECTION, limit=1000, offset=offset,
            with_vectors=[DENSE_VEC], with_payload=True,
        )
        for p in pts:
            pay = p.payload or {}
            if pay.get("source_type") == "raptor_summary":
                continue
            pg = pay.get("page_number")
            if pg is None or pay.get("is_content") is False:
                continue
            if cfg.min_content_page > 0 and pg < cfg.min_content_page:
                continue
            if cfg.max_content_page > 0 and pg > cfg.max_content_page:
                continue
            if pay.get("tenant_id") not in (cfg.global_tenant_id, "global", None):
                continue
            vec = p.vector
            if isinstance(vec, dict):
                cand = [v for k, v in vec.items() if k.startswith("dense_") and len(v) > 64]
                if not cand:
                    continue
                vec = max(cand, key=len)
            if vec is None:
                continue
            vectors.append(vec)
            pages.append(int(pg))
            texts.append(pay.get("text") or "")
        if offset is None:
            break
    m = np.asarray(vectors, dtype=np.float64)
    m /= (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)
    return m, np.asarray(pages, dtype=np.int64), texts


def scroll_corpus_flags(client, cfg) -> dict:
    """Every chunk (in window OR not): the STALE stored `is_content`, and what the CURRENT filter
    says about the TEXT, split by band and by window membership.

    This is what makes the pre-registration's F1 error legible: the arm's pool is the WINDOW, and
    244 of the corpus's 263 rejects sit outside it. Guard C4 uses the stored column (which must NOT
    be what the arm is built on); C2 uses the whole-corpus band split.
    """
    stored: Counter = Counter()
    corpus_band: Counter = Counter()
    corpus_in_window: Counter = Counter()
    band_pages: dict[str, list[int]] = defaultdict(list)
    n_chunks = 0
    offset = None
    while True:
        pts, offset = client.scroll(collection_name=COLLECTION, limit=1000, offset=offset,
                                    with_vectors=False, with_payload=True)
        for p in pts:
            pay = p.payload or {}
            if pay.get("source_type") == "raptor_summary":
                continue
            n_chunks += 1
            stored[str(pay.get("is_content"))] += 1
            pg = pay.get("page_number")
            in_win = pg is not None and cfg.min_content_page <= pg <= cfg.max_content_page
            corpus_in_window["in_window" if in_win else "out_of_window"] += 1
            text = pay.get("text") or ""
            if not is_content(text):
                b = band_of(text) or "other"
                corpus_band[b] += 1
                corpus_in_window["flagged_in_window" if in_win else "flagged_out_of_window"] += 1
                if pg is not None:
                    band_pages[b].append(int(pg))
        if offset is None:
            break
    return {
        "n_chunks": n_chunks,
        "stored_is_content": stored,
        "corpus_band": corpus_band,
        "window_split": corpus_in_window,
        "band_page_ranges": {b: [min(v), max(v), len(v)] for b, v in band_pages.items()},
    }


def reachable_pages(cfg) -> set[int]:
    """§I58 ceiling: a page with >=1 chunk, `is_content is not False`, inside the content window."""
    from sqlmodel import Session, select

    from src.core.database import Chunk, get_engine
    with Session(get_engine(cfg)) as session:
        rows = session.exec(
            select(Chunk).where(Chunk.document_id.like(f"{NEW_DOC}%"))  # type: ignore[attr-defined]
        ).all()
    return {
        int(c.page_number) for c in rows
        if c.page_number is not None and c.is_content is not False
        and cfg.min_content_page <= c.page_number <= cfg.max_content_page
    }


# ── metric (verbatim from `embedder_screen.py` == §I63) ───────────────────────────────────────

def rank_pages(sims: np.ndarray, pages: np.ndarray, k: int) -> list[int]:
    """Distinct pages in rank order — a page scores once, at its best chunk's rank."""
    idx = np.argsort(-sims)[:k]
    seen, out = set(), []
    for i in idx:
        pg = int(pages[i])
        if pg in seen:
            continue
        seen.add(pg)
        out.append(pg)
    return out


def paired_ci(diffs: list[float]) -> dict:
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "sd": None, "ci95": None, "resolved": None,
                "direction": None, "wlt": None}
    m = statistics.mean(diffs)
    sd = statistics.stdev(diffs) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    lo, hi = m - half, m + half
    w = sum(1 for d in diffs if d < 0)
    l = sum(1 for d in diffs if d > 0)
    t = sum(1 for d in diffs if d == 0)
    return {"n": n, "mean": round(m, 6), "sd": round(sd, 6),
            "ci95": [round(lo, 6), round(hi, 6)],
            "resolved": bool(lo > 0 or hi < 0),
            "direction": ("T>C" if lo > 0 else "T<C" if hi < 0 else "straddles 0"),
            "wlt": {"T_worse": w, "T_better": l, "tie": t}}


def agg(rows: list[dict], arm: str, embedder: str, key: str) -> dict:
    out = {}
    for k in KS:
        vals = [r["arms"][arm][embedder][f"{key}{k}"] for r in rows
                if r["arms"].get(arm, {}).get(embedder, {}).get(f"{key}{k}") is not None]
        out[f"R@{k}"] = round(statistics.mean(vals), 6) if vals else None
        out[f"n_queries_{key}@{k}"] = len(vals)
    return out


def band_of(text: str) -> str | None:
    """Which §I39 signal rejects this chunk — in `is_content`'s OWN check order."""
    if any(m in text.lower()[:500] for m in NON_CHAPTER_MARKERS):
        return "front_matter"
    if is_index_heading(text):
        return "index"
    if not any(ch.isalnum() for ch in text):
        return "furniture"
    if is_index_layout(text):
        return "index"
    if is_toc_layout(text):
        return "toc"
    if is_index_density(text):
        return "index"
    return None


def exact(got: dict, want: dict) -> dict:
    d = {k: {"this_run": got.get(k), "registered": want[k],
             "match": got.get(k) is not None and abs(got[k] - want[k]) < 1e-9} for k in want}
    d["pass"] = all(v["match"] for k, v in d.items() if k != "pass")
    return d


# ── main ──────────────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--control-batch", type=int, default=64)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.", file=sys.stderr)
        return 4

    t0 = time.time()
    cfg = get_settings()
    verifiers: dict = {}

    # ── X2 — the resolved config names the REMOTE store (§I49 Finding 1) ──────────────────────
    host = (cfg.qdrant_host or "").strip()
    x2 = {"qdrant_host": host, "qdrant_collection": cfg.qdrant_collection,
          "min_content_page": cfg.min_content_page, "max_content_page": cfg.max_content_page,
          "global_tenant_id": cfg.global_tenant_id,
          "pass": bool(cfg.qdrant_collection == COLLECTION and host and host not in ("localhost", "127.0.0.1"))}
    verifiers["X2_resolved_target"] = x2
    print(f"X2: host={host!r} collection={cfg.qdrant_collection!r} "
          f"window=[{cfg.min_content_page},{cfg.max_content_page}] pass={x2['pass']}")
    if not x2["pass"]:
        print("ABORT: run with QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2.",
              file=sys.stderr)
        return 3

    # ── the corpus and the queries ────────────────────────────────────────────────────────────
    store = DocumentStore(cfg)
    client = store._qdrant  # noqa: SLF001
    m_q, pages, texts = scroll_pool(client, cfg)
    print(f"pool: {m_q.shape[0]} in-window chunks x {m_q.shape[1]}d  ({time.time()-t0:.0f}s)")

    reach_all = reachable_pages(cfg)
    print(f"reachable pages (SQLite, §I58): {len(reach_all)}")

    raw = json.loads(QUERIES.read_text(encoding="utf-8"))
    queries = [q for q in raw
               if isinstance(q, dict) and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    if args.limit:
        queries = queries[: args.limit]
    print(f"queries: {len(queries)}")

    # ── the flag, computed from the TEXT (pre-reg F1 / guard C4) ──────────────────────────────
    flags = [is_content(t) for t in texts]
    flagged_idx = [i for i, ok in enumerate(flags) if not ok]
    keep = np.asarray([ok for ok in flags], dtype=bool)
    band_counts = Counter(band_of(texts[i]) for i in flagged_idx)

    # ── the WHOLE CORPUS, in window or not — the scan that exposes the pre-registration's F1 ──
    corpus_scan = scroll_corpus_flags(client, cfg)
    corpus_band = corpus_scan["corpus_band"]
    window_split = corpus_scan["window_split"]
    stored_false = corpus_scan["stored_is_content"]

    print(f"IN-POOL flagged by the CURRENT filter (from text): {len(flagged_idx)}  "
          f"bands={dict(band_counts)}")
    print(f"CORPUS flagged: {sum(corpus_band.values())}  bands={dict(corpus_band)}  "
          f"page ranges={corpus_scan['band_page_ranges']}")
    print(f"CORPUS window split: {dict(window_split)}")
    print(f"stored is_content values (whole corpus): {dict(stored_false)}")

    # ── C4 — built from the TEXT, not the stored column ───────────────────────────────────────
    c4 = {
        "flagged_from_text": len(flagged_idx),
        "expected_in_pool_flagged": EXPECTED_IN_POOL_FLAGGED,
        "stored_is_content_values": {k: v for k, v in stored_false.items()},
        "stored_is_content_False": int(stored_false.get("False", 0)),
        "would_be_a_5_chunk_treatment": int(stored_false.get("False", 0)),
        "expected_stored_false": EXPECTED_STORED_FALSE,
        "corpus_flagged_from_text": sum(corpus_band.values()),
        "expected_corpus_flagged": EXPECTED_CORPUS_FLAGGED,
    }
    c4["pass"] = bool(c4["flagged_from_text"] == EXPECTED_IN_POOL_FLAGGED
                      and c4["stored_is_content_False"] == EXPECTED_STORED_FALSE
                      and c4["corpus_flagged_from_text"] == EXPECTED_CORPUS_FLAGGED
                      and c4["flagged_from_text"] != c4["stored_is_content_False"])
    verifiers["C4_treatment_from_text_not_column"] = c4
    print(f"C4: in-pool flagged from text={c4['flagged_from_text']} "
          f"(expected {EXPECTED_IN_POOL_FLAGGED}), corpus={c4['corpus_flagged_from_text']} "
          f"(expected {EXPECTED_CORPUS_FLAGGED}), stored False={c4['stored_is_content_False']}  "
          f"pass={c4['pass']}")

    # ── C2 — the treatment pool is exactly C minus the flagged chunks; bands match §I39 ───────
    # C2′ (re-registration): the IN-POOL count is the treatment's size; the CORPUS count is
    # reported as the context the pre-registration mistook for it.
    n_kept = int(keep.sum())
    corpus_band_matches = {b: {"this_run": corpus_band.get(b, 0), "registered": n,
                               "match": corpus_band.get(b, 0) == n}
                           for b, n in I39_BANDS.items()}
    corpus_band_matches["furniture"] = {"this_run": corpus_band.get("furniture", 0),
                                        "registered": 0,
                                        "match": corpus_band.get("furniture", 0) == 0}
    c2 = {
        "pool_C": int(m_q.shape[0]),
        "flagged_in_pool": len(flagged_idx),
        "pool_T": n_kept,
        "T_equals_C_minus_flagged": bool(int(m_q.shape[0]) - len(flagged_idx) == n_kept),
        "expected_pool": EXPECTED_POOL,
        "pool_C_matches_I70": bool(int(m_q.shape[0]) == EXPECTED_POOL),
        "expected_in_pool_flagged": EXPECTED_IN_POOL_FLAGGED,
        "in_pool_flagged_matches": bool(len(flagged_idx) == EXPECTED_IN_POOL_FLAGGED),
        "in_pool_bands": dict(band_counts),
        "corpus_bands": corpus_band_matches,
        "corpus_flagged": sum(corpus_band.values()),
        "corpus_window_split": dict(window_split),
        "corpus_flagged_out_of_window": window_split.get("flagged_out_of_window", 0),
        "expected_corpus_flagged_out_of_window": EXPECTED_CORPUS_FLAGGED_OUT_OF_WINDOW,
        "band_page_ranges": corpus_scan["band_page_ranges"],
    }
    c2["pass"] = bool(c2["T_equals_C_minus_flagged"] and c2["pool_C_matches_I70"]
                      and c2["in_pool_flagged_matches"]
                      and c2["corpus_flagged_out_of_window"] == EXPECTED_CORPUS_FLAGGED_OUT_OF_WINDOW
                      and all(v["match"] for v in corpus_band_matches.values()))
    verifiers["C2_pool_partition_and_bands"] = c2
    print(f"C2: pool_C={c2['pool_C']} - flagged={len(flagged_idx)} = pool_T={n_kept}  "
          f"in-pool bands={dict(band_counts)}  corpus bands="
          f"{ {k: v['this_run'] for k, v in corpus_band_matches.items()} }  "
          f"out-of-window={c2['corpus_flagged_out_of_window']}  pass={c2['pass']}")

    # ── the ceilings, per arm (pre-reg §2: the ceiling MOVES; report both) ────────────────────
    pages_C = {int(p) for p in pages}
    kept_pages = {int(p) for p in pages[keep]}
    lost_pages = sorted(pages_C - kept_pages)          # pages with no unflagged chunk left
    reach_C = set(reach_all)
    reach_T = reach_all - set(lost_pages)
    print(f"pages covered: C={len(pages_C)}  T={len(kept_pages)}  "
          f"pages lost from the ceiling={len(lost_pages)}")
    print(f"ceiling (§I58 reachable ∩ relevant, per arm): C={len(reach_C)}  T={len(reach_T)}")

    # ── X1 — the Qdrant pool and the SQLite ceiling describe the same page set ────────────────
    x1 = {
        "pages_in_pool_C": len(pages_C), "reachable_pages_sqlite": len(reach_C),
        "expected_reachable_pages": EXPECTED_REACHABLE_PAGES,
        "matches_I70_artifact": bool(len(reach_C) == EXPECTED_REACHABLE_PAGES),
        "pool_only": sorted(pages_C - reach_C)[:20], "sqlite_only": sorted(reach_C - pages_C)[:20],
        "n_pool_only": len(pages_C - reach_C), "n_sqlite_only": len(reach_C - pages_C),
    }
    x1["pass"] = bool(pages_C == reach_C and x1["matches_I70_artifact"])
    verifiers["X1_pool_pages_eq_reachable_pages"] = x1
    print(f"X1: pool pages == SQLite reachable pages = {x1['pass']} "
          f"(pool-only {x1['n_pool_only']}, sqlite-only {x1['n_sqlite_only']})")

    # ── C6 — one shared `pages` array across arms ─────────────────────────────────────────────
    c6 = {"pages_array_sha256": hashlib.sha256(pages.tobytes()).hexdigest(),
          "n_chunks": int(pages.shape[0]), "n_arms": 2,
          "one_shared_pages_array": True}   # by construction: one `pages`, one rank_pages
    c6["pass"] = True
    verifiers["C6_shared_page_mapping"] = c6

    # ── the two embedders ─────────────────────────────────────────────────────────────────────
    # PRIMARY gemma@768: embed the pool ONCE; the arms differ only in which rows are in it.
    corpus: dict[str, np.ndarray] = {"qwen3": m_q}
    embed_seconds: dict[str, float] = {}
    t = time.time()
    corpus["gemma"] = cluster_embed([GEMMA_DOC_PREFIX + x for x in texts],
                                    batch=args.batch, model=GEMMA_HF)
    embed_seconds["gemma"] = round(time.time() - t, 1)
    print(f"embedded gemma: {corpus['gemma'].shape} in {embed_seconds['gemma']}s")

    # C3 — A-vs-A: the SAME corpus re-embedded at a different batch size must be byte-identical.
    t = time.time()
    m_ctrl = cluster_embed([GEMMA_DOC_PREFIX + x for x in texts],
                           batch=args.control_batch, model=GEMMA_HF)
    embed_seconds["gemma_control"] = round(time.time() - t, 1)
    c3 = {
        "model": GEMMA_HF, "batch_a": args.batch, "batch_b": args.control_batch,
        "max_abs_diff": float(np.max(np.abs(corpus["gemma"] - m_ctrl)))
        if corpus["gemma"].shape == m_ctrl.shape else None,
        "n_rows_differing": int(np.sum(np.any(corpus["gemma"] != m_ctrl, axis=1)))
        if corpus["gemma"].shape == m_ctrl.shape else None,
    }
    c3["vectors_identical"] = bool(c3["max_abs_diff"] == 0.0)
    verifiers["C3_A_vs_A_control_vectors"] = c3
    print(f"C3(a): A-vs-A re-embed batch {args.batch} vs {args.control_batch} "
          f"max_abs_diff={c3['max_abs_diff']} rows_differing={c3['n_rows_differing']}")

    # query vectors — each embedder on its own path (§I62: the cluster applies NO prefixes)
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    qwen = get_cluster_embedder(cfg)      # the production query path (instruction applied)
    qvec: dict[str, np.ndarray] = {}
    v = np.asarray([qwen.embed_query(q["query"]) for q in queries], dtype=np.float64)
    qvec["qwen3"] = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)
    v = cluster_embed([GEMMA_QRY_PREFIX + q["query"] for q in queries],
                      batch=len(queries), model=GEMMA_HF)
    qvec["gemma"] = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)
    print("query vectors ready")

    # ── the arms ──────────────────────────────────────────────────────────────────────────────
    # An arm is (embedder, row subset). Every arm ranks the SAME `pages` array, same metric code.
    arm_rows: dict[str, np.ndarray] = {"C": np.arange(len(pages)), "T": np.where(keep)[0]}
    arm_reach: dict[str, set[int]] = {"C": reach_C, "T": reach_T}
    arm_vectors: dict[str, dict[str, np.ndarray]] = {
        a: {e: corpus[e][idx] for e in ("gemma", "qwen3")} for a, idx in arm_rows.items()
    }
    arm_vectors["C_ctrl"] = {"gemma": m_ctrl}      # C3(b): arm C re-run on the control vectors

    # ⚠️ Each arm ranks ITS OWN rows, so it must score against ITS OWN page array — a subset view
    # of the one shared `pages` (guard C6). Ranking the subset's similarities against the FULL
    # `pages` array would read every arm's pages from the wrong offset and silently inflate it.
    arm_pages: dict[str, np.ndarray] = {a: pages[idx] for a, idx in arm_rows.items()}

    def score_arm(sims: np.ndarray, arm: str, relevant: set[int], ceil: set[int]) -> dict:
        rk_all = rank_pages(sims, arm_pages[arm], len(arm_pages[arm]))
        out = {
            **{f"c{j}": (round(len(set(rk_all[:j]) & ceil) / len(ceil), 6) if ceil else None)
               for j in KS},
            **{f"r{j}": (round(len(set(rk_all[:j]) & relevant) / len(relevant), 6)
                         if relevant else None) for j in KS},
            "n_pages_in_pool": len(rk_all),
            "ceiling_size": len(ceil),
        }
        return out

    results: list[dict] = []
    errors: list[dict] = []
    empty_ceiling: list[dict] = []
    c3_metric_mismatches: list[dict] = []
    t3 = time.time()
    for i, q in enumerate(queries, 1):
        qid = q["id"]
        relevant = {int(p) for p in q["relevant_pages"]}
        row = {"id": qid, "query_type": q.get("query_type"),
               "n_relevant": len(relevant), "arms": {}}
        for arm in ("C", "T"):
            ceil = relevant & arm_reach[arm]
            row["arms"][arm] = {"n_reachable": len(ceil)}
            if not ceil:
                empty_ceiling.append({"id": qid, "arm": arm, "n_relevant": len(relevant)})
            for e in ("gemma", "qwen3"):
                try:
                    sims = arm_vectors[arm][e] @ qvec[e][i - 1]
                except Exception as exc:  # noqa: BLE001
                    errors.append({"id": qid, "arm": arm, "embedder": e,
                                   "error": f"{type(exc).__name__}: {exc}"})
                    continue
                row["arms"][arm][e] = score_arm(sims, arm, relevant, ceil)
            # C3(b) — arm C re-run on the control vectors must be byte-identical to arm C.
            # ⚠️ It must be scored against arm C's OWN ceiling (`relevant & reach_C`), not the raw
            # `reach_C` — passing the wrong ceiling here is what made the FIRST run report 266
            # spurious metric mismatches on bit-identical vectors. A control compared under a
            # different denominator is not a control.
            try:
                ceil_C = relevant & reach_C
                sims_c = arm_vectors["C_ctrl"]["gemma"] @ qvec["gemma"][i - 1]
                ctrl = score_arm(sims_c, "C", relevant, ceil_C)
                base = row["arms"]["C"].get("gemma", {})
                bad = {k: (base.get(k), ctrl.get(k)) for k in ctrl
                       if k in base and base.get(k) != ctrl.get(k)}
                if bad:
                    c3_metric_mismatches.append({"id": qid, "fields": bad})
            except Exception as exc:  # noqa: BLE001
                errors.append({"id": qid, "arm": "C_ctrl", "embedder": "gemma",
                               "error": f"{type(exc).__name__}: {exc}"})
        results.append(row)
        if i % 25 == 0:
            print(f"  [{i}/{len(queries)}] {qid} … {time.time()-t3:.0f}s", flush=True)

    c3["metric_mismatches"] = len(c3_metric_mismatches)
    c3["metric_mismatch_detail"] = c3_metric_mismatches[:10]
    c3["pass"] = bool(c3["vectors_identical"] and c3["metric_mismatches"] == 0)
    print(f"C3(b): arm C on the control vectors — {c3['metric_mismatches']} metric mismatch(es), "
          f"pass={c3['pass']}")

    # ── C5 — every query with an empty reachable set is reported ──────────────────────────────
    c5 = {"n_queries": len(results),
          "queries_with_empty_ceiling": empty_ceiling,
          "n_empty_ceiling": len(empty_ceiling),
          "n_queries_C_with_ceiling": sum(1 for r in results if r["arms"]["C"]["n_reachable"] > 0),
          "n_queries_T_with_ceiling": sum(1 for r in results if r["arms"]["T"]["n_reachable"] > 0),
          "pass": True}   # C5 is a REPORTING guard: it fails only if a query was dropped silently
    dropped = [r["id"] for r in results
               if r["arms"]["C"]["n_reachable"] > 0 and "gemma" not in r["arms"]["C"]]
    c5["queries_dropped_silently"] = dropped
    c5["pass"] = bool(not dropped)
    verifiers["C5_empty_ceiling_reported"] = c5
    print(f"C5: {len(empty_ceiling)} query/arm(s) with an empty ceiling; "
          f"C has {c5['n_queries_C_with_ceiling']}, T has {c5['n_queries_T_with_ceiling']}")

    # ── the aggregates ────────────────────────────────────────────────────────────────────────
    arms_agg = {a: {e: {"ceiling_norm": agg(results, a, e, "c"), "raw": agg(results, a, e, "r")}
                    for e in ("gemma", "qwen3")} for a in ("C", "T")}

    # ── C1 — arm C reproduces §I70's qwen3@1024 row EXACTLY ───────────────────────────────────
    c1 = exact(arms_agg["C"]["qwen3"]["ceiling_norm"], I70_QWEN3_1024)
    verifiers["C1_reproduces_I70_qwen3_1024"] = c1
    print("C1: " + " ".join(f"{k}={v['this_run']}" for k, v in c1.items() if k != "pass")
          + f"  pass={c1['pass']}")

    # ── the endpoints: T − C, paired, per embedder ────────────────────────────────────────────
    endpoints: dict = {}
    for e in ("gemma", "qwen3"):
        endpoints[e] = {}
        for key, label in (("c", "ceiling_norm"), ("r", "raw")):
            for k in KS:
                diffs = [r["arms"]["T"][e][f"{key}{k}"] - r["arms"]["C"][e][f"{key}{k}"]
                         for r in results
                         if r["arms"].get("T", {}).get(e, {}).get(f"{key}{k}") is not None
                         and r["arms"].get("C", {}).get(e, {}).get(f"{key}{k}") is not None]
                endpoints[e][f"{label}_R@{k}_T_minus_C"] = paired_ci(diffs)

    primary = endpoints["gemma"]["ceiling_norm_R@20_T_minus_C"]
    decision = {
        "primary_embedder": "gemma@768",
        "endpoint": "paired ceiling-normalised R@20, arm T − arm C, n = 133",
        "delta": primary["mean"], "ci95": primary["ci95"], "n": primary["n"],
        "wlt": primary["wlt"],
        "ATTRIBUTABLE": bool(primary["resolved"]),
        "reads": ("the content filter MOVES base-lane page ranking"
                  if primary["resolved"] and (primary["mean"] or 0) > 0
                  else "the content filter LOWERS base-lane page ranking"
                  if primary["resolved"] else
                  "applying the content filter does not move base-lane page ranking on this "
                  "corpus (a RESULT, not an unresolved one)"),
        "resolution_floor_n133": round(1.96 * (primary["sd"] or 0.0) / math.sqrt(primary["n"]), 6)
        if primary["n"] else None,
    }

    chunk_stats = {
        "n_chunks_C": int(m_q.shape[0]), "n_chunks_T": n_kept,
        "pages_C": len(pages_C), "pages_T": len(kept_pages),
        "chunks_per_page_C": round(len(pages_C) and m_q.shape[0] / len(pages_C), 4),
        "chunks_per_page_T": round(len(kept_pages) and n_kept / len(kept_pages), 4),
        "chars_median_C": sorted(len(t) for t in texts)[len(texts) // 2],
    }

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/chunk_filter_ab.py",
            "preregistration":
                ".hermes/plans/2026-10-24-p1-chunking-filter-ab-preregistration.md",
            "preregistration_commit": "aa4b55b",
            "reregistration":
                ".hermes/plans/2026-10-24-p1-chunk-filter-ab-reregistration.md",
            "first_run_void": {
                "artifact": "logs/p1/step10/chunk_filter_ab_firstrun_VOID.json",
                "sha256": "0b25fd3467d68c8244efc38c1406f64f9554c81836ad67a067829da4bc584916",
                "void_on": ["C2", "C4", "C3"],
                "reasons": {
                    "C2/C4": ("a PRE-REGISTRATION PREMISE ERROR, not a harness bug: F1's "
                              "\"263 (6.9 %)\" is the WHOLE-CORPUS count; this arm's pool is the "
                              "content window (3,489 chunks), and 244 of the 263 rejects sit "
                              "outside it (index 186 on pages 937-968 > 936; front matter 5 on "
                              "pages 2-14 < 30; TOC 72 on pages 22-34, of which only 19 are "
                              "in-window). The treatment is 19 chunks. Restated as C2'/C4'."),
                    "C3": ("a HARNESS BUG: the control arm was scored against the raw reachable "
                           "set instead of arm C's own per-query ceiling, so 266 metric "
                           "'mismatches' were reported on BIT-IDENTICAL vectors "
                           "(max_abs_diff 0.0, 0 rows differing). Fixed."),
                },
                "endpoint_unchanged": ("the arm definition was faithful throughout - T is C minus "
                                       "the filter's rejects; only the registered SIZE and the "
                                       "control's denominator were wrong"),
            },
            "what": ("§I71 arm 1 — isolates the CONTENT-FILTER STATE: does applying the CURRENT "
                     "`content_filter.is_content()` to the shipped pool move base-lane PAGE "
                     "ranking? Same stored vectors, same queries, same metric code; the pool "
                     "filter is the only variable."),
            "why_no_reingest": ("the filter changes which chunks are in the candidate pool, not "
                                "any chunk's text, id or vector — so it is measurable over the "
                                "vectors already stored (pre-reg §2)"),
            "corpus": NEW_DOC, "collection": COLLECTION,
            "pool_size": int(m_q.shape[0]), "reachable_pages": len(reach_all),
            "chunk_stats": chunk_stats,
            "embed_url": EMBED_URL,
            "models": {"gemma": {"hf": GEMMA_HF, "dim": 768, "doc_prefix": GEMMA_DOC_PREFIX,
                                 "qry_prefix": GEMMA_QRY_PREFIX},
                       "qwen3": {"hf": "Qwen/Qwen3-Embedding-0.6B", "dim": 1024,
                                 "source": "stored dense_1024 (late-chunked at ingest)"}},
            "arms": {"C": "the shipped pool (§I70's)", "T": "C minus the CURRENT filter's rejects"},
            "ks": list(KS), "hyde": "OFF (raw query vectors)",
            "late_chunking_asymmetry": ("qwen3@1024 ranks the STORED dense_1024 vectors (produced "
                                        "with late chunking); gemma@768 embeds the chunk text "
                                        "directly. Same asymmetry §I63/§I70 carried."),
            "endpoint": "paired ceiling-normalised R@20, T − C, n=133, under gemma@768",
            "preregistered_rule": ("attributable iff the 95 % CI excludes 0; otherwise the honest "
                                   "statement is a RESULT of no movement, not an unresolved one"),
            "no_llm_calls": True, "no_writes_to_collections": True,
            "embed_seconds": embed_seconds,
            "wall_seconds": round(time.time() - t0, 1),
        },
        "verifiers": verifiers,
        "arms": arms_agg,
        "endpoints": endpoints,
        "decision": decision,
        "queries": results,
    }
    Path(args.out).write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    h = hashlib.sha256(Path(args.out).read_bytes()).hexdigest()
    print(f"\nwrote {args.out}\nsha256 {h}")

    print("\n=== ceiling-normalised R@20 / raw R@20, per arm and embedder ===")
    print(f"  {'arm':>4} {'embedder':>8} {'cR@20':>9} {'cR@100':>9} {'rawR@20':>9} {'rawR@100':>9}")
    for a in ("C", "T"):
        for e in ("gemma", "qwen3"):
            ca = arms_agg[a][e]["ceiling_norm"]
            ra = arms_agg[a][e]["raw"]
            print(f"  {a:>4} {e:>8} {ca['R@20']:>9.4f} {ca['R@100']:>9.4f} "
                  f"{ra['R@20']:>9.4f} {ra['R@100']:>9.4f}")

    print("\n=== the endpoint: paired T − C ===")
    for e in ("gemma", "qwen3"):
        for label in ("ceiling_norm", "raw"):
            d = endpoints[e][f"{label}_R@20_T_minus_C"]
            ci = d["ci95"]
            print(f"  {e:>6} {label:>13} R@20  Δ {d['mean']:+.6f} "
                  f"[{ci[0]:+.6f},{ci[1]:+.6f}] n={d['n']} "
                  f"{'RESOLVED' if d['resolved'] else 'UNRESOLVED'}  W/L/T "
                  f"{d['wlt']['T_worse']}/{d['wlt']['T_better']}/{d['wlt']['tie']}")

    print(f"\n  pages covered  C={len(pages_C)}  T={len(kept_pages)}  "
          f"(lost from the ceiling: {len(lost_pages)})")
    print(f"  chunks/page    C={chunk_stats['chunks_per_page_C']}  "
          f"T={chunk_stats['chunks_per_page_T']}")

    print("\nverifiers: " + "  ".join(f"{k.split('_')[0]}={v['pass']}"
                                      for k, v in verifiers.items()))
    return 0 if all(v["pass"] for v in verifiers.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
