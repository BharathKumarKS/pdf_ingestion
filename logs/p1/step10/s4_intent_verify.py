#!/usr/bin/env python
"""S4 verifier — the intent classifier retrain (plan §3 Stage D, Verifier D).

  V1  the NEW classifier loads and `n_features_in_ == 768`; the OLD one is 1024 (both read from
      the artifacts, not from a log).
  V2  the router's LOAD GUARD is real: an `IntentRouter` built with the nomic (768) config and
      pointed at the 1024-trained pickle must REFUSE to load it (`_clf is None`) — that is the
      whole reason this stage is not optional (`intent_router.py:156`).
  V3  the router loads the NEW classifier under the nomic config and it predicts on a real vector.
  V4  HELD-OUT COMPARISON on the 133 gold queries: the new (768/nomic) vs the old (1024/Qwen3)
      classifier, each embedded with ITS OWN model. Reported as a comparison — a regression is a
      finding, not a blocker.
  V5  the new classifier is not degenerate: it emits more than one class on the gold set.

Run:
    unset PYTHONPATH
    export DENSE_MODEL=nomic-ai/nomic-embed-text-v1.5 DENSE_DIM=768 DENSE_DIM_LOW=64 \
           QUERY_INSTRUCTION="search_query: " DOCUMENT_PREFIX="search_document: "
    uv run python -u logs/p1/step10/s4_intent_verify.py \
        --old-clf /Users/bharathkumar/.hermes/cache/scratch/intent_classifier_1024d_qwen3.pkl.bak
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

QWEN_INSTR = ("Instruct: Given a physics question, retrieve textbook passages that answer it\nQuery: ")


def load_gold() -> list[dict]:
    raw = json.loads((REPO / "data/eval_queries_v2.json").read_text())
    q = [x for x in raw if isinstance(x, dict)
         and str(x.get("id", "")).startswith(("gold-", "ovw-")) and (x.get("relevant_pages") or [])]
    return sorted(q, key=lambda x: x["id"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-clf", required=True, help="path to the 1024-trained pickle (backup)")
    ap.add_argument("--new-clf", default="data/models/intent_classifier.pkl")
    args = ap.parse_args()

    import joblib
    from src.core.config import Settings, get_settings
    from src.core.intent_router import IntentRouter
    from src.pdf_ingestion.cluster_embedder import ClusterDenseEmbedder

    cfg = get_settings()                     # nomic, from the env
    new = joblib.load(REPO / args.new_clf)
    old = joblib.load(args.old_clf)

    results: list[tuple[str, bool, str]] = []

    # ── V1: the two artifacts' widths ────────────────────────────────────────
    n_new, n_old = int(new.n_features_in_), int(old.n_features_in_)
    results.append(("V1 new clf is 768 / old is 1024",
                    n_new == 768 and n_old == 1024 and cfg.dense_dim == 768,
                    f"new={n_new} old={n_old} cfg.dense_dim={cfg.dense_dim}"))

    # ── V2: the load guard refuses a mismatched classifier ───────────────────
    guarded = Settings(intent_classifier_path=str(args.old_clf), dense_dim=768, dense_dim_low=64,
                       dense_model=cfg.dense_model, query_instruction=cfg.query_instruction,
                       document_prefix=cfg.document_prefix, use_stub_embedder=False)
    r_bad = IntentRouter(settings=guarded)
    results.append(("V2 router REFUSES the 1024 clf under a 768 config",
                    r_bad._clf is None, "guard fired (clf not loaded)" if r_bad._clf is None
                    else "!! guard did NOT fire"))

    # ── V3: the router loads the new classifier ──────────────────────────────
    good = Settings(intent_classifier_path=str(REPO / args.new_clf), dense_dim=768, dense_dim_low=64,
                    dense_model=cfg.dense_model, query_instruction=cfg.query_instruction,
                    document_prefix=cfg.document_prefix, use_stub_embedder=False)
    r_ok = IntentRouter(settings=good)
    emb = ClusterDenseEmbedder(settings=cfg)
    probe_vec = emb.embed_query("What is Newton's second law?")
    intent = r_ok.classify(probe_vec) if r_ok._clf is not None else None
    results.append(("V3 router loads the new clf and predicts",
                    r_ok._clf is not None and intent is not None,
                    f"clf loaded; classify('What is Newton's second law?') -> {intent}"))

    # ── V4: held-out comparison on the 133 gold queries ──────────────────────
    gold = load_gold()
    texts = [q["query"] for q in gold]
    y_true = [q["query_type"] for q in gold]

    # ⚠️ Build each model's embedder EXPLICITLY — `get_cluster_embedder` is a memoised singleton,
    # so asking for the old model via the factory would silently reuse the nomic instance.
    qwen = Settings(dense_model="Qwen/Qwen3-Embedding-0.6B", dense_dim=1024, dense_dim_low=64,
                    query_instruction=QWEN_INSTR, document_prefix="", use_stub_embedder=False)
    emb_new = ClusterDenseEmbedder(settings=cfg)
    emb_old = ClusterDenseEmbedder(settings=qwen)

    X_new = np.array([emb_new.embed_query(t) for t in texts], dtype=np.float32)
    X_old = np.array([emb_old.embed_query(t) for t in texts], dtype=np.float32)

    p_new = [str(x) for x in new.predict(X_new)]
    p_old = [str(x) for x in old.predict(X_old)]
    acc_new = float(np.mean([a == b for a, b in zip(p_new, y_true)]))
    acc_old = float(np.mean([a == b for a, b in zip(p_old, y_true)]))
    delta = acc_new - acc_old
    by_type = {}
    for t in sorted(set(y_true)):
        idx = [i for i, v in enumerate(y_true) if v == t]
        by_type[t] = {"n": len(idx),
                      "new": round(float(np.mean([p_new[i] == t for i in idx])), 4),
                      "old": round(float(np.mean([p_old[i] == t for i in idx])), 4)}
    # The plan's criterion is "at least as well as" — so this CAN fail, and a regression is
    # reported as a finding rather than hidden. (Absolute agreement is moderate: the synthetic
    # training set does not transfer perfectly to real gold queries — say so, do not bury it.)
    results.append((f"V4 gold agreement new={acc_new:.4f} >= old={acc_old:.4f} (delta {delta:+.4f})",
                    acc_new >= acc_old, f"n={len(gold)}; per-type {by_type}"))

    # ── V5: not degenerate ───────────────────────────────────────────────────
    dist = collections.Counter(p_new)
    results.append(("V5 new clf is not a constant predictor",
                    len(dist) > 1, f"predicted classes on gold: {dict(dist)}"))

    # ── V6: the destination is queryable by a REAL query (not a count) ───────
    # The plan's Stage E asks for "every lane asserted non-empty by a real query, not by a count".
    # This runs the product's own funnel against the destination with a nomic query vector.
    v6_ok, v6_detail = False, "not run"
    try:
        from src.pdf_ingestion.store import DocumentStore
        store = DocumentStore(cfg)
        qv = emb_new.embed_query("What is Newton's second law?")
        hits = store.search(qv, tenant_id="global", limit=5)
        v6_ok = len(hits) > 0
        top = hits[0] if hits else {}
        v6_detail = (f"{len(hits)} hit(s) from the product funnel; top chunk "
                     f"{str(top.get('chunk_id'))[:8]} page {top.get('page_number')} "
                     f"score {top.get('score')}")
    except Exception as exc:  # noqa: BLE001
        v6_detail = f"{type(exc).__name__}: {exc}"
    results.append(("V6 destination answers a real query through the funnel", v6_ok, v6_detail))

    print(f"\nnew clf: {args.new_clf} ({n_new}d) | old clf: {args.old_clf} ({n_old}d)")
    print(f"gold: {len(gold)} queries, types {dict(collections.Counter(y_true))}")
    ok = True
    for name, passed, detail in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}: {detail}")
        ok = ok and passed
    print(f"\n{'ALL PASS' if ok else 'FAILED'}")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
