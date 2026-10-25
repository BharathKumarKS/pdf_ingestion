#!/usr/bin/env python
"""§1 of the embedder-screen plan — the cross-embedder SCREEN.

Plan: `.hermes/plans/2026-10-24-p1-embedder-screen-hyde-cache-and-finetune-plan.md` §1.
Instrument: §I63's `cross_embedder_experiment.py`, unchanged in its metric code (the helpers below
are copied verbatim so V3/V4/V5 can be EXACT reproductions of registered rows).

What this is
------------
An **ORACLE screen**, not the product. Hold the corpus fixed (new doc `7ba61432`, 3,489 in-window
chunks), swap only the embedder, score by **exact brute-force cosine** over the whole corpus
(page-deduped) — not Qdrant, because §I60 measured up to 18.5 % of the pool lost to the filtered-HNSW
path. 133 gold queries, endpoint **R@20 paired, ceiling-normalised** (§I58). **HyDE OFF** (raw query
vectors) so the comparison is not confounded by the generator. No LLM calls, no writes.

Candidates — each at ITS OWN smallest trained MRL slot AND at full dim (owner decision 2026-10-23;
do not force a fixed 64d):

    qwen3  Qwen/Qwen3-Embedding-0.6B            1024  MRL 32-1024      incumbent (the stored index)
    nomic  nomic-ai/nomic-embed-text-v1.5        768  MRL 64-768       §I63's known-best (+0.1400)
    gemma  google/embeddinggemma-300m            768  MRL 512/256/128  NO 64d slot (forces a new vector)
    mpnet  tomaarsen/mpnet-base-nli-matryoshka   768  MRL 768..64      NLI-trained, not retrieval

Pre-registered decision rule (fixed before the run, plan §1): a candidate must beat **BOTH** the
incumbent (qwen3@1024) **and** nomic@768 on paired ceiling-normalised R@20 with a CI excluding 0,
before a re-ingest is even costed. nomic must be in the comparison because it already beats the
incumbent — losing to nomic is not an improvement whatever it does against qwen3.

⚠️ Known asymmetry, recorded not hidden: the incumbent arm ranks the **stored** `dense_1024` vectors,
which were produced by the production ingest WITH late chunking (per-token mean over the parent).
Every other arm embeds the chunk text directly, i.e. WITHOUT late chunking. So a new model that wins
does so against a late-chunked incumbent (conservative); a new model that loses might be losing to
late chunking, not to the model. §I63 carried the same asymmetry for nomic.

Traps carried in (all measured — do not re-derive)
--------------------------------------------------
* The endpoint **IGNORES a `dimensions` param** (sending 128 returns 768/1024). Slice client-side
  and re-normalise. Guard V9 asserts it live.
* §I62's prefix trap: the cluster is a **generic passthrough** and applies NO task prefixes. The
  caller must prefix. Guard V1 measures this per model (raw vs prefixed cosine).
* gemma's prompts are asymmetric: `task: search result | query: ` for queries,
  `title: none | text: ` for documents (Google EmbeddingGemma docs / transformers model_doc).
* mpnet ships `prompts: {"query": "", "document": ""}` — no prefix (its own
  `config_sentence_transformers.json`).
* qwen3 documents carry NO instruction; only the query side does (`cfg.query_instruction`).

Verifiers (each must be able to FAIL)
-------------------------------------
  V1  the cluster is a passthrough for every prefixed model: cos(raw, prefixed) < 0.999 on real
      chunks, AND for nomic the prefixed vector reproduces the LOCAL `NomicEmbedder` (cos >= 0.9999).
  V2  A-vs-A negative control: one model re-embedded at a different batch size — byte-identical.
  V3  qwen3@1024 reproduces §I60's d=1024 row EXACTLY (every-chunk pool).
  V4  qwen3@1024 reproduces §I59's `new_fulldim` row EXACTLY (top-1000-chunk pool).
  V5  qwen3@64  reproduces §I59's `new_mrl64` row EXACTLY (top-1000-chunk pool) — validates that a
      client-side MRL slice of the stored 1024d vector IS the stored 64d lane.
  V6  every arm ranks the SAME `pages` array and sees identical n_relevant.
  V7  every query that errors is reported and excluded, never silently dropped.
  V8  slice sanity: each low-dim vector is unit-norm and is exactly the truncation of its full vector.
  V9  the endpoint ignores `dimensions` (ask for 128, get the native dim back).
  V10 all four models are served, at their expected native dims.
  V11 nomic@768 reproduces §I63's arm N EXACTLY — a second script reproducing the first script's
      baseline, which is what makes the baselines trustworthy.
  V12 the INCUMBENT's query path applies `cfg.query_instruction` (V1 skips qwen3, so this was the one
      prefix nothing asserted). Raised by the independent reviewer; see the note at the call site.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python logs/p1/step10/embedder_screen.py
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
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.embedder import get_embedder  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

QUERIES = REPO / "data/eval_queries_v2.json"
OUT = REPO / "logs/p1/step10/embedder_screen.json"

NEW_DOC = "7ba61432"
COLLECTION = "knowledge_base_v2"
DENSE_VEC = "dense_1024"

EMBED_URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"

KS = (20, 100, 500, 1000)

# ── the candidate spec ────────────────────────────────────────────────────────────────────────
# `low` is each model's OWN smallest trained MRL slot (plan §1) — not a forced 64d.
MODELS: list[dict] = [
    {
        "key": "qwen3", "hf": "Qwen/Qwen3-Embedding-0.6B", "native": 1024, "low": 32,
        "source": "stored", "doc_prefix": None, "qry_prefix": "cfg.query_instruction",
        "note": "incumbent; MRL 32-1024; documents carry no instruction",
    },
    {
        "key": "nomic", "hf": "nomic-ai/nomic-embed-text-v1.5", "native": 768, "low": 64,
        "source": "cluster", "doc_prefix": "search_document: ", "qry_prefix": "search_query: ",
        "note": "§I63's known-best on this corpus (+0.1400); MRL 64-768",
    },
    {
        "key": "gemma", "hf": "google/embeddinggemma-300m", "native": 768, "low": 128,
        "source": "cluster", "doc_prefix": "title: none | text: ",
        "qry_prefix": "task: search result | query: ",
        "note": "NO 64d slot -> adopting it forces a new named vector; asymmetric prompts",
    },
    {
        "key": "mpnet", "hf": "tomaarsen/mpnet-base-nli-matryoshka", "native": 768, "low": 64,
        "source": "cluster", "doc_prefix": "", "qry_prefix": "",
        "note": "NLI-trained, not retrieval; MatryoshkaLoss dims 768/512/256/128/64",
    },
]

# Reference arms that are NOT candidates but anchor the screen to registered numbers.
# qwen3@64 is the SHIPPED low lane; V5 uses it to prove the client-side slice is the stored lane.
REFERENCE_SLOTS = {"qwen3": [64]}

BASELINES = ("qwen3@1024", "nomic@768")

# §I60's new_index d=1024 row (ceiling-normalised, EVERY-chunk pool) — V3 must reproduce EXACTLY.
I60_D1024_NEW = {"R@20": 0.293934, "R@100": 0.569074, "R@500": 0.922982, "R@1000": 1.0}
# §I59's `new_fulldim` row (ceiling-normalised, TOP-1000-chunk pool) — V4 must reproduce EXACTLY.
I59_FULLDIM_NEW = {"R@20": 0.293934, "R@100": 0.569074, "R@500": 0.922421, "R@1000": 0.926563}
# §I59's `new_mrl64` row (ceiling-normalised, TOP-1000-chunk pool) — V5 must reproduce EXACTLY.
I59_MRL64_NEW = {"R@20": 0.102763, "R@100": 0.358682, "R@500": 0.788044, "R@1000": 0.815136}
# §I63's arm N (nomic 768d, ceiling-normalised, EVERY-chunk pool) — V11 must reproduce EXACTLY.
# A second script reproducing the first script's baseline is what makes the baselines trustworthy.
I63_NOMIC_768 = {"R@20": 0.43393, "R@100": 0.628993, "R@500": 0.927347, "R@1000": 1.0}

# EmbeddingGemma's input window (its model card: "Maximum input context length of 2048 tokens").
# Estimated at 4.5 chars/token — §I52 measured 4.49-4.53 chars/token on real physics text.
GEMMA_TOKEN_WINDOW = 2048
CHARS_PER_TOKEN = 4.5


# ── cluster HTTP (generalised from §I63's `cluster_embed`) ────────────────────────────────────

def cluster_embed(texts: list[str], batch: int, model: str) -> np.ndarray:
    """Pooled vectors from the cluster, L2-normalised. Batched; honours the response `index`."""
    out: list[np.ndarray] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i:i + batch]
        body = json.dumps({"model": model, "input": chunk}).encode()
        req = urllib.request.Request(EMBED_URL, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            d = json.load(r)
        items = sorted(d["data"], key=lambda x: x.get("index", 0))
        for it in items:
            out.append(np.asarray(it["embedding"], dtype=np.float64))
    m = np.asarray(out, dtype=np.float64)
    return m / (np.linalg.norm(m, axis=1, keepdims=True) + 1e-12)


def cluster_probe(model: str, text: str, dimensions: int | None = None) -> tuple[int, np.ndarray]:
    """One text, one model; optionally ask for `dimensions`. Returns (dim, unit vector)."""
    body: dict = {"model": model, "input": [text]}
    if dimensions is not None:
        body["dimensions"] = dimensions
    req = urllib.request.Request(EMBED_URL, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.load(r)
    v = np.asarray(d["data"][0]["embedding"], dtype=np.float64)
    return int(v.shape[0]), v / (np.linalg.norm(v) + 1e-12)


# ── reads (verbatim from §I63) ────────────────────────────────────────────────────────────────

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


# ── metric (verbatim from §I63) ───────────────────────────────────────────────────────────────

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


def mrl_slice_matrix(m: np.ndarray, dim: int) -> np.ndarray:
    """Row-wise MRL truncation: first `dim` coords, re-normalised (cosine assumes unit norm)."""
    low = np.asarray(m[:, :dim], dtype=np.float64).copy()
    return low / (np.linalg.norm(low, axis=1, keepdims=True) + 1e-12)


def mrl_slice(vec: np.ndarray, dim: int) -> np.ndarray:
    low = np.asarray(vec[:dim], dtype=np.float64).copy()
    return low / (float(np.linalg.norm(low)) + 1e-12)


def paired_ci(diffs: list[float]) -> dict:
    n = len(diffs)
    if n == 0:
        return {"n": 0, "mean": None, "ci95": None, "resolved": None, "wlt": None}
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
            "direction": ("cand>base" if lo > 0 else "cand<base" if hi < 0 else "straddles 0"),
            "wlt": {"cand_worse": w, "cand_better": l, "tie": t}}


def agg(rows: list[dict], arm: str, key: str) -> dict:
    out = {}
    for k in KS:
        vals = [r["arms"][arm][f"{key}{k}"] for r in rows
                if r.get("arms") and r["arms"].get(arm) and r["arms"][arm].get(f"{key}{k}") is not None]
        out[f"R@{k}"] = round(statistics.mean(vals), 6) if vals else None
    return {"queries": len(rows), **out}


# ── main ──────────────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--batch", type=int, default=128)
    ap.add_argument("--control-batch", type=int, default=64)
    ap.add_argument("--skip-embed", action="store_true",
                    help="reuse vectors cached in the artifact (debug only)")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if Path(args.out).exists() and not args.force:
        print(f"REFUSING to overwrite {args.out} without --force.", file=sys.stderr)
        return 4

    cfg = get_settings()
    if cfg.qdrant_collection != COLLECTION:
        print(f"ABORT: QDRANT_COLLECTION is {cfg.qdrant_collection!r}, expected {COLLECTION!r}. "
              f"Run with QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION={COLLECTION}.",
              file=sys.stderr)
        return 3

    raw = json.loads(QUERIES.read_text(encoding="utf-8"))
    queries = [q for q in raw
               if isinstance(q, dict) and str(q.get("id", "")).startswith(("gold-", "ovw-"))
               and (q.get("relevant_pages") or [])]
    queries.sort(key=lambda q: q["id"])
    if args.limit:
        queries = queries[: args.limit]
    print(f"queries: {len(queries)}")

    t0 = time.time()
    store = DocumentStore(cfg)
    client = store._qdrant  # noqa: SLF001
    m_q, pages, texts = scroll_pool(client, cfg)
    print(f"pool: {m_q.shape[0]} in-window chunks x {m_q.shape[1]}d  ({time.time()-t0:.0f}s)")

    reach = reachable_pages(cfg)
    print(f"reachable pages (ceiling): {len(reach)}")

    verifiers: dict = {}

    # ── V10 — all four models are served, at their expected native dims ───────────────────────
    probe_text = "search_document: entropy is a measure of the number of microscopic configurations"
    v10: dict = {}
    for spec in MODELS:
        try:
            dim, _ = cluster_probe(spec["hf"], probe_text)
            v10[spec["key"]] = {"served": True, "dim": dim, "expected": spec["native"],
                                "match": dim == spec["native"]}
        except Exception as exc:  # noqa: BLE001
            v10[spec["key"]] = {"served": False, "error": f"{type(exc).__name__}: {exc}",
                                "match": False}
    v10["pass"] = all(v.get("match") for k, v in v10.items() if isinstance(v, dict) and k != "pass")
    verifiers["V10_models_served"] = v10
    print(f"V10: " + "  ".join(
        f"{k}={v.get('dim')}/{v.get('expected')}" for k, v in v10.items() if isinstance(v, dict)))
    if not v10["pass"]:
        print("ABORT: a candidate model is not served at its expected dim.", file=sys.stderr)
        return 5

    # ── V9 — the endpoint ignores a `dimensions` param ────────────────────────────────────────
    v9: dict = {}
    for spec in MODELS:
        d_asked, _ = cluster_probe(spec["hf"], probe_text, dimensions=128)
        v9[spec["key"]] = {"asked": 128, "got": d_asked, "ignored": d_asked == spec["native"]}
    v9["pass"] = all(v["ignored"] for k, v in v9.items() if k != "pass")
    verifiers["V9_dimensions_ignored"] = v9
    print(f"V9: dimensions param ignored on all models = {v9['pass']}")

    # ── V1 — the cluster is a passthrough (prefixes matter), per model; + nomic vs local ──────
    probe_idx = [i for i, t in enumerate(texts) if t and len(t) > 200][:5]
    probe_chunks = [texts[i] for i in probe_idx]
    probe_queries = [q["query"] for q in queries[:5]]
    v1: dict = {}
    local = get_embedder(cfg)          # the LOCAL NomicEmbedder — the reference for nomic only
    loc_doc = np.asarray(local.embed_documents(probe_chunks), dtype=np.float64)
    loc_doc /= (np.linalg.norm(loc_doc, axis=1, keepdims=True) + 1e-12)
    loc_q = np.asarray([local.embed_query(t) for t in probe_queries], dtype=np.float64)
    loc_q /= (np.linalg.norm(loc_q, axis=1, keepdims=True) + 1e-12)
    # The probe prefix is the model's OWN prefix where it has one, and the DOC and QUERY sides are
    # probed with their own prefixes (they are asymmetric for every prefixed model here — getting
    # this wrong silently compares a document-prefixed query against a query-prefixed one, which is
    # how the first version of this guard FAILED, correctly). A no-prefix model (mpnet) gets a
    # sentinel instead: sending raw and sending "sentinel + text" MUST give different vectors, which
    # is what proves the endpoint passes the text through rather than stripping/normalising it.
    # (Comparing a model's raw text against its own raw text would be the §I63 "check that cannot
    # fail" trap — identical by construction.)
    for spec in MODELS:
        if spec["source"] != "cluster":
            continue
        doc_pp = spec["doc_prefix"] or "ZZZ-PASSTHROUGH-PROBE: "
        qry_pp = spec["qry_prefix"] or "ZZZ-PASSTHROUGH-PROBE: "
        raw_doc = cluster_embed(probe_chunks, batch=len(probe_chunks), model=spec["hf"])
        pre_doc = cluster_embed([doc_pp + t for t in probe_chunks],
                                batch=len(probe_chunks), model=spec["hf"])
        raw_q = cluster_embed(probe_queries, batch=len(probe_queries), model=spec["hf"])
        pre_q = cluster_embed([qry_pp + t for t in probe_queries],
                              batch=len(probe_queries), model=spec["hf"])
        # and the vectors must depend on the TEXT (not a constant / stub endpoint)
        a, b = cluster_embed([probe_chunks[0], probe_chunks[1]], batch=2, model=spec["hf"])
        entry = {
            "doc_probe_prefix": doc_pp, "qry_probe_prefix": qry_pp,
            "doc_cos_raw_vs_prefixed": round(float(np.mean(np.sum(raw_doc * pre_doc, axis=1))), 6),
            "qry_cos_raw_vs_prefixed": round(float(np.mean(np.sum(raw_q * pre_q, axis=1))), 6),
            "two_different_chunks_cos": round(float(np.sum(a * b)), 6),
            "prefix_changes_the_vector": bool(
                np.mean(np.sum(raw_doc * pre_doc, axis=1)) < 0.999
                and np.mean(np.sum(raw_q * pre_q, axis=1)) < 0.999),
            "vectors_depend_on_text": bool(float(np.sum(a * b)) < 0.999),
        }
        if spec["key"] == "nomic":      # the one model we can reproduce locally (§I63's X1)
            entry["doc_cos_vs_local_prefixed"] = round(float(np.mean(np.sum(loc_doc * pre_doc, axis=1))), 6)
            entry["doc_cos_vs_local_raw"] = round(float(np.mean(np.sum(loc_doc * raw_doc, axis=1))), 6)
            entry["qry_cos_vs_local_prefixed"] = round(float(np.mean(np.sum(loc_q * pre_q, axis=1))), 6)
            entry["reproduces_local"] = bool(
                entry["doc_cos_vs_local_prefixed"] >= 0.9999
                and entry["qry_cos_vs_local_prefixed"] >= 0.9999)
        entry["pass"] = bool(entry["prefix_changes_the_vector"] and entry["vectors_depend_on_text"]
                             and entry.get("reproduces_local", True))
        v1[spec["key"]] = entry
    v1["pass"] = all(v["pass"] for k, v in v1.items() if k != "pass")
    verifiers["V1_cluster_is_a_passthrough"] = v1
    print(f"V1: " + "  ".join(
        f"{k}(raw/pre cos {v['doc_cos_raw_vs_prefixed']:.4f})" for k, v in v1.items() if k != "pass")
        + f"  nomic_reproduces_local={v1['nomic'].get('reproduces_local')}  pass={v1['pass']}")

    # ── embed every cluster model over the SAME corpus ────────────────────────────────────────
    corpus: dict[str, np.ndarray] = {"qwen3": m_q}
    qvec: dict[str, np.ndarray] = {}
    embed_seconds: dict[str, float] = {}
    for spec in MODELS:
        k = spec["key"]
        if spec["source"] == "stored":
            continue
        t = time.time()
        corpus[k] = cluster_embed([spec["doc_prefix"] + x for x in texts],
                                  batch=args.batch, model=spec["hf"])
        embed_seconds[k] = round(time.time() - t, 1)
        print(f"  embedded {k}: {corpus[k].shape[0]} chunks x {corpus[k].shape[1]}d "
              f"in {embed_seconds[k]}s")

    # ── V2 — A-vs-A negative control: re-embed one model at a different batch size ────────────
    ctrl_key = "nomic"
    spec = next(s for s in MODELS if s["key"] == ctrl_key)
    m_ctrl = cluster_embed([spec["doc_prefix"] + x for x in texts],
                           batch=args.control_batch, model=spec["hf"])
    v2 = {
        "model": ctrl_key, "batch_a": args.batch, "batch_b": args.control_batch,
        "max_abs_diff": float(np.max(np.abs(corpus[ctrl_key] - m_ctrl)))
        if corpus[ctrl_key].shape == m_ctrl.shape else None,
        "n_mismatch": int(np.sum(np.any(corpus[ctrl_key] != m_ctrl, axis=1)))
        if corpus[ctrl_key].shape == m_ctrl.shape else None,
    }
    v2["pass"] = bool(v2["max_abs_diff"] == 0.0)
    verifiers["V2_A_vs_A_control"] = v2
    print(f"V2: A-vs-A batch {args.batch} vs {args.control_batch} "
          f"max_abs_diff={v2['max_abs_diff']} mismatch={v2['n_mismatch']} pass={v2['pass']}")

    # ── query vectors, per model, on its own path ─────────────────────────────────────────────
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
    qwen = get_cluster_embedder(cfg)      # the production query path (instruction applied)
    for spec in MODELS:
        k = spec["key"]
        if k == "qwen3":
            v = np.asarray([qwen.embed_query(q["query"]) for q in queries], dtype=np.float64)
        else:
            v = cluster_embed([spec["qry_prefix"] + q["query"] for q in queries],
                              batch=len(queries), model=spec["hf"])
        qvec[k] = v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)
    print("query vectors ready")

    # ── V12 — the INCUMBENT's query path applies the production instruction ───────────────────────
    # ⚠️ Raised by the independent reviewer (deleg_1dd4aa6a) and it is a real hole: V1 skips qwen3
    # because its DOCUMENT vectors are the STORED index vectors rather than a cluster call, so the
    # query-side prefix of the baseline everything is measured against was the one prefix nothing
    # asserted. A silent change to `cfg.query_instruction` would have moved the baseline with no
    # guard failing. (It was in fact pinned indirectly — V3/V4/V5/V11 reproduce four rows produced by
    # other scripts through this same path, so a change would break all four — but indirect is not
    # asserted.) This closes it directly.
    _qp = queries[0]["query"]
    _v_prod = np.asarray(qwen.embed_query(_qp), dtype=np.float64)
    _v_prod /= (np.linalg.norm(_v_prod) + 1e-12)
    _v_direct = cluster_embed([cfg.query_instruction + _qp], batch=1, model=cfg.dense_model)[0]
    _v_raw = cluster_embed([_qp], batch=1, model=cfg.dense_model)[0]
    v12 = {
        "instruction": cfg.query_instruction,
        "instruction_non_empty": bool(cfg.query_instruction.strip()),
        "cos_production_vs_direct": round(float(np.sum(_v_prod * _v_direct)), 6),
        "cos_production_vs_raw": round(float(np.sum(_v_prod * _v_raw)), 6),
        "instruction_changes_the_vector": bool(float(np.sum(_v_prod * _v_raw)) < 0.999),
    }
    v12["pass"] = bool(
        v12["instruction_non_empty"]
        and float(np.sum(_v_prod * _v_direct)) >= 0.99999
        and v12["instruction_changes_the_vector"])
    verifiers["V12_qwen3_query_instruction"] = v12
    print(f"V12: production query path == instruction+text (cos {v12['cos_production_vs_direct']}), "
          f"raw cos {v12['cos_production_vs_raw']}, pass={v12['pass']}")

    # ── arms ──────────────────────────────────────────────────────────────────────────────────
    # An arm is (model, slot). Every arm ranks the SAME `pages` array with the SAME metric code.
    arm_specs: list[tuple[str, int, str]] = []
    for spec in MODELS:
        k = spec["key"]
        arm_specs.append((k, spec["native"], "full"))
        arm_specs.append((k, spec["low"], "own-smallest-MRL"))
        for extra in REFERENCE_SLOTS.get(k, []):
            arm_specs.append((k, extra, "reference"))

    arm_names = [f"{k}@{d}" for k, d, _ in arm_specs]

    # V8 — slice sanity, computed once per (model, slot): unit norm + exact truncation identity
    v8: dict = {}
    for spec in MODELS:
        k = spec["key"]
        for dim in [spec["low"], *REFERENCE_SLOTS.get(k, [])]:
            low = mrl_slice_matrix(corpus[k], dim)
            norms = np.linalg.norm(low, axis=1)
            trunc = corpus[k][:, :dim] / (np.linalg.norm(corpus[k][:, :dim], axis=1, keepdims=True) + 1e-12)
            v8[f"{k}@{dim}"] = {
                "max_norm_error": float(np.max(np.abs(norms - 1.0))),
                "is_exact_truncation": bool(np.array_equal(low, trunc)),
                "pass": bool(float(np.max(np.abs(norms - 1.0))) < 1e-9
                             and np.array_equal(low, trunc)),
            }
    v8["pass"] = all(v["pass"] for k, v in v8.items() if k != "pass")
    verifiers["V8_slice_sanity"] = v8

    results: list[dict] = []
    errors: list[dict] = []
    t3 = time.time()
    for i, q in enumerate(queries, 1):
        qid = q["id"]
        relevant = {int(p) for p in q["relevant_pages"]}
        ceil = relevant & reach
        row = {"id": qid, "query_type": q.get("query_type"),
               "n_relevant": len(relevant), "n_reachable": len(ceil), "arms": {}}
        for (k, dim, kind) in arm_specs:
            arm = f"{k}@{dim}"
            try:
                if dim == corpus[k].shape[1]:
                    sims = corpus[k] @ qvec[k][i - 1]
                else:
                    sims = mrl_slice_matrix(corpus[k], dim) @ mrl_slice(qvec[k][i - 1], dim)
            except Exception as exc:  # noqa: BLE001
                errors.append({"id": qid, "arm": arm, "error": f"{type(exc).__name__}: {exc}"})
                continue
            rk_all = rank_pages(sims, pages, len(pages))
            rk_1k = rank_pages(sims, pages, 1000)
            row["arms"][arm] = {
                **{f"r{j}": (round(len(set(rk_all[:j]) & relevant) / len(relevant), 6)
                             if relevant else None) for j in KS},
                **{f"c{j}": (round(len(set(rk_all[:j]) & ceil) / len(ceil), 6) if ceil else None)
                   for j in KS},
                **{f"p1000_c{j}": (round(len(set(rk_1k[:j]) & ceil) / len(ceil), 6)
                                   if ceil else None) for j in KS},
                "n_pages_in_pool": len(rk_all),
                "n_pages_in_pool_top1000": len(rk_1k),
            }
        results.append(row)
        if i % 25 == 0:
            print(f"  [{i}/{len(queries)}] {qid} … {time.time()-t3:.0f}s", flush=True)

    # ── V6 — one shared pages array, identical n_relevant across every arm ────────────────────
    complete = [r for r in results if all(a in r["arms"] for a in arm_names)]
    v6 = {
        "pool_size": int(m_q.shape[0]),
        "pages_array_sha256": hashlib.sha256(pages.tobytes()).hexdigest()[:16],
        "n_arms": len(arm_names),
        "n_queries_with_every_arm": len(complete),
        "all_arms_share_one_pages_array": True,   # by construction: one `pages`, one rank_pages
        "n_relevant_identical_across_arms": all(
            len({r["arms"][a]["n_pages_in_pool"] for a in arm_names}) == 1 for r in complete),
    }
    v6["pass"] = bool(v6["n_relevant_identical_across_arms"]
                      and v6["n_queries_with_every_arm"] == len(results))
    verifiers["V6_shared_pages_array"] = v6

    # ── V7 — errors reported, never silently dropped ──────────────────────────────────────────
    v7 = {"n_errors": len(errors), "errors": errors, "n_queries_kept": len(results),
          "pass": len(errors) == 0}
    verifiers["V7_errors_reported"] = v7
    print(f"V7: {v7['n_errors']} error(s), {len(results)} queries kept")

    arms_agg = {a: {"raw": agg(results, a, "r"), "ceiling_norm": agg(results, a, "c"),
                    "ceiling_norm_top1000pool": agg(results, a, "p1000_c")} for a in arm_names}

    # ── V3/V4/V5 — exact reproductions of registered rows ─────────────────────────────────────
    def exact(name: str, got: dict, want: dict) -> dict:
        d = {k: {"this_run": got[k], "registered": want[k],
                 "match": got[k] is not None and abs(got[k] - want[k]) < 1e-9} for k in want}
        d["pass"] = all(v["match"] for k, v in d.items() if k != "pass")
        return d

    verifiers["V3_I60_d1024_everychunk"] = exact(
        "I60", arms_agg["qwen3@1024"]["ceiling_norm"], I60_D1024_NEW)
    verifiers["V4_I59_new_fulldim_top1000"] = exact(
        "I59_new_fulldim", arms_agg["qwen3@1024"]["ceiling_norm_top1000pool"], I59_FULLDIM_NEW)
    verifiers["V5_I59_new_mrl64_top1000"] = exact(
        "I59_new_mrl64", arms_agg["qwen3@64"]["ceiling_norm_top1000pool"], I59_MRL64_NEW)
    verifiers["V11_I63_nomic_768_everychunk"] = exact(
        "I63_arm_N", arms_agg["nomic@768"]["ceiling_norm"], I63_NOMIC_768)
    for vid in ("V3_I60_d1024_everychunk", "V4_I59_new_fulldim_top1000",
                "V5_I59_new_mrl64_top1000", "V11_I63_nomic_768_everychunk"):
        print(f"{vid[:2]}: pass={verifiers[vid]['pass']}  "
              + " ".join(f"{k}={v['this_run']}" for k, v in verifiers[vid].items() if k != "pass"))

    # ── the endpoints: every arm vs both baselines, paired, ceiling-normalised ────────────────
    endpoints: dict = {}
    for arm in arm_names:
        if arm in BASELINES:
            continue
        endpoints[arm] = {}
        for base in BASELINES:
            for key, label in (("c", "ceiling_norm"), ("r", "raw")):
                for k in KS:
                    diffs = [r["arms"][arm][f"{key}{k}"] - r["arms"][base][f"{key}{k}"]
                             for r in results
                             if r["arms"].get(arm, {}).get(f"{key}{k}") is not None
                             and r["arms"].get(base, {}).get(f"{key}{k}") is not None]
                    endpoints[arm][f"{label}_R@{k}_vs_{base}"] = paired_ci(diffs)

    # ── the pre-registered rule, evaluated mechanically ───────────────────────────────────────
    decision: dict = {}
    for arm in arm_names:
        if arm in BASELINES:
            continue
        e_q = endpoints[arm]["ceiling_norm_R@20_vs_qwen3@1024"]
        e_n = endpoints[arm]["ceiling_norm_R@20_vs_nomic@768"]
        decision[arm] = {
            "delta_vs_qwen3@1024": e_q["mean"], "ci_vs_qwen3@1024": e_q["ci95"],
            "beats_qwen3": bool(e_q["resolved"] and e_q["mean"] > 0),
            "delta_vs_nomic@768": e_n["mean"], "ci_vs_nomic@768": e_n["ci95"],
            "beats_nomic": bool(e_n["resolved"] and e_n["mean"] > 0),
        }
        decision[arm]["PASSES_the_rule"] = bool(decision[arm]["beats_qwen3"]
                                                and decision[arm]["beats_nomic"])

    # ── chunk-length context, for the one model with a tight input window ──────────────────────
    # EmbeddingGemma truncates at 2048 tokens. Tokens are ESTIMATED (chars / 4.5, §I52's measured
    # chars-per-token on real physics text), so this is context for reading gemma@768, not a
    # measurement of truncation.
    char_lens = sorted(len(t) for t in texts)
    n = len(char_lens)
    over = sum(1 for c in char_lens if c / CHARS_PER_TOKEN > GEMMA_TOKEN_WINDOW)
    chunk_stats = {
        "n_chunks": n,
        "chars_median": char_lens[n // 2] if n else None,
        "chars_p90": char_lens[int(n * 0.9)] if n else None,
        "chars_max": char_lens[-1] if n else None,
        "est_tokens_max": round(char_lens[-1] / CHARS_PER_TOKEN, 1) if n else None,
        "gemma_window_tokens": GEMMA_TOKEN_WINDOW,
        "chunks_over_gemma_window_est": over,
        "frac_over_gemma_window_est": round(over / n, 6) if n else None,
    }

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/embedder_screen.py",
            "plan": ".hermes/plans/2026-10-24-p1-embedder-screen-hyde-cache-and-finetune-plan.md §1",
            "what": ("the embedder SCREEN — an oracle, not the product: hold the corpus fixed, "
                     "swap only the embedder, exact brute-force cosine, 133 gold queries"),
            "why_exact_search": ("§I60 showed Qdrant's filtered-HNSW path costs up to 18.5 % of the "
                                 "pool; exact cosine removes that confound"),
            "corpus": NEW_DOC, "collection": COLLECTION,
            "pool_size": int(m_q.shape[0]), "reachable_pages": len(reach),
            "chunk_char_stats": chunk_stats,
            "embed_url": EMBED_URL,
            "models": {s["key"]: {k: v for k, v in s.items() if k != "key"} for s in MODELS},
            "arms": arm_names, "baselines": list(BASELINES), "ks": list(KS),
            "hyde": "OFF (raw query vectors) — the screen must not be confounded by the generator",
            "late_chunking_asymmetry": ("qwen3@1024 ranks the STORED dense_1024 vectors (produced "
                                        "with late chunking); every other arm embeds the chunk text "
                                        "directly. Same asymmetry §I63 carried for nomic."),
            "preregistered_rule": ("a candidate must beat BOTH qwen3@1024 and nomic@768 on paired "
                                   "ceiling-normalised R@20 with a CI excluding 0, before a "
                                   "re-ingest is even costed"),
            "no_llm_calls": True, "no_writes": True,
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

    print("\n=== ceiling-normalised R@20, every arm (baselines marked *) ===")
    print(f"  {'arm':>26} {'R@20':>9} {'R@100':>9} {'Δ vs qwen3@1024':>18} {'Δ vs nomic@768':>18}")
    for arm in arm_names:
        a = arms_agg[arm]["ceiling_norm"]
        e_q = endpoints.get(arm, {}).get("ceiling_norm_R@20_vs_qwen3@1024")
        e_n = endpoints.get(arm, {}).get("ceiling_norm_R@20_vs_nomic@768")
        mark = "*" if arm in BASELINES else " "
        fq = (f"{e_q['mean']:+.4f} [{e_q['ci95'][0]:+.4f},{e_q['ci95'][1]:+.4f}]"
              if e_q else "—")
        fn = (f"{e_n['mean']:+.4f} [{e_n['ci95'][0]:+.4f},{e_n['ci95'][1]:+.4f}]"
              if e_n else "—")
        print(f" {mark}{arm:>25} {a['R@20']:>9.4f} {a['R@100']:>9.4f} {fq:>18} {fn:>18}")

    print("\n=== the pre-registered rule ===")
    for arm, d in decision.items():
        print(f"  {arm:>26}  beats_qwen3={d['beats_qwen3']}  beats_nomic={d['beats_nomic']}"
              f"  => PASSES={d['PASSES_the_rule']}")

    print("\nverifiers: " + "  ".join(f"{k.split('_')[0]}={v['pass']}"
                                      for k, v in verifiers.items()))
    return 0 if all(v["pass"] for v in verifiers.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
