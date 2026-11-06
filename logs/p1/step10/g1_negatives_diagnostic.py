#!/usr/bin/env python3
"""G1 pre-flight diagnostic — READ-ONLY re-derivation over an EXISTING artifact.

Question: can the INPUT guardrail (G1) be built from the cheap signals the plan names —
a top-1 retrieval-score floor, and/or an off-topic (domain) signal — on the 34 negatives
in data/eval_queries_v2.json?

This is NOT a run. It reads the product-config run already on disk
(data/eval_results/v3_judged_full_2026-11-03_0115.json — knowledge_base_v3 / nomic-768,
DA+SPLADE+ColBERT+MMR on, CE on) and re-derives, per query, the recorded top-1 cross-encoder
score. Every cell below is re-derivable from the artifact's own `top_chunks`.

Output: logs/p1/step10/g1_negatives_diagnostic.json
No cluster, no writes to any store.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "data/eval_results/v3_judged_full_2026-11-03_0115.json"
OUT = ROOT / "logs/p1/step10/g1_negatives_diagnostic.json"

REFUSE_IF_BELOW = "top1_ce_score < tau"  # the direction the existing logic assumes


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _top1(r: dict):
    tc = r.get("top_chunks") or []
    return tc[0].get("score") if tc else None


def _subclass(qid: str) -> str:
    if qid.startswith("neg-out"):
        return "out"      # off-domain (capital of France)
    if qid.startswith("neg-in"):
        return "in"       # in-domain physics the book does NOT cover (Higgs boson)
    if qid.startswith("neg-nea"):
        return "nea"      # in-domain, book lacks the specific value (top-quark mass)
    return "other"


def _auc(pts: list[tuple[float, bool]]) -> float:
    """AUC for `refuse if score < tau`: P(score_neg < score_ans), ties = 0.5."""
    neg = [s for s, is_neg in pts if is_neg]
    ans = [s for s, is_neg in pts if not is_neg]
    if not neg or not ans:
        return float("nan")
    c = 0.0
    for s in neg:
        c += sum(1 for s2 in ans if s2 > s) + 0.5 * sum(1 for s2 in ans if s2 == s)
    return c / (len(neg) * len(ans))


def main() -> None:
    data = json.loads(SRC.read_text())
    results = data["results"]
    pts = [(_top1(r), r.get("answerable") is False) for r in results if _top1(r) is not None]
    N = sum(1 for _, n in pts if n)
    A = sum(1 for _, n in pts if not n)

    # Queries the text-lane signal cannot score at all: the 33 `vis-*` queries ran the ColPali
    # page lane (page-level MaxSim), which records no chunk-level top-1. A text score floor is
    # undefined for them — the gate must be defined PER ROUTE.
    excluded = [r for r in results if _top1(r) is None]
    excluded_by_type: dict[str, int] = {}
    for r in excluded:
        excluded_by_type[r.get("query_type", "?")] = excluded_by_type.get(r.get("query_type", "?"), 0) + 1

    subclasses: dict[str, list[float]] = {}
    for r in results:
        if r.get("answerable") is False:
            s = _top1(r)
            if s is not None:
                subclasses.setdefault(_subclass(r["id"]), []).append(s)

    def _op(tau: float) -> dict:
        tp = sum(1 for s, n in pts if n and s < tau)
        fp = sum(1 for s, n in pts if (not n) and s < tau)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / N
        fpr = fp / A
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        return {"tau": tau, "tp": tp, "fp": fp, "precision": round(prec, 4),
                "recall": round(rec, 4), "false_refusal_rate": round(fpr, 4), "f1": round(f1, 4)}

    # Pre-registered operating-point rule: the LOWEST tau whose false-refusal rate <= budget,
    # then report the recall it buys. (The curve is the result; a single tau is a reading.)
    def _op_at_fpr(budget: float) -> dict | None:
        best = None
        for i in range(0, 401):
            tau = i / 200
            o = _op(tau)
            if o["false_refusal_rate"] <= budget:
                if best is None or o["tp"] > best["tp"]:
                    best = o
        return best

    pr_curve = [_op(i / 200) for i in range(0, 401)]

    out = {
        "kind": "read-only re-derivation (no run, no cluster, no store write)",
        "question": "Can the INPUT guardrail be built from a top-1 score floor and/or an off-topic signal?",
        "source_artifact": str(SRC.relative_to(ROOT)),
        "source_sha256": _sha256(SRC),
        "source_config": {
            "collection": data["config_snapshot"]["retriever"]["collection"],
            "dense_model": data["config_snapshot"]["embedding"]["model"],
            "dense_dim": data["config_snapshot"]["embedding"]["dim"],
            "da_enabled": data["config_snapshot"]["derivative_artifacts"]["enabled"],
            "splade_enabled": data["config_snapshot"]["retriever"]["splade_enabled"],
            "colbert": data["config_snapshot"]["colbert"]["enabled"],
            "mmr_enabled": data["config_snapshot"]["mmr"]["enabled"],
            "reranker": data["config_snapshot"]["reranker"]["model"],
            "score_threshold": data["config_snapshot"]["score_threshold"],
        },
        "population": {"n_scored": len(pts), "answerable": A, "negatives": N},
        "excluded_from_signal": {
            "n": len(excluded),
            "by_query_type": excluded_by_type,
            "reason": "no chunk-level top-1 (visual/ColPali route) — a text score floor is undefined; "
                      "the gate must be defined per route",
        },
        "signal": "top1 cross-encoder score (top_chunks[0].score, recorded per query)",
        "decision_rule": REFUSE_IF_BELOW,
        "auc_refuse_if_below": round(_auc(pts), 4),
        "negative_subclasses": {
            k: {
                "n": len(v),
                "scores": [round(x, 4) for x in sorted(v)],
                "min": round(min(v), 4),
                "median": round(sorted(v)[len(v) // 2], 4),
                "max": round(max(v), 4),
            }
            for k, v in sorted(subclasses.items())
        },
        "mechanism_ceilings": {
            "domain_classifier_recall_ceiling": round(len(subclasses.get("out", [])) / N, 4),
            "note_domain": "an off-topic/domain signal can only catch the `out` subclass",
        },
        "operating_points_by_false_refusal_budget": {
            "fpr<=0.05": _op_at_fpr(0.05),
            "fpr<=0.10": _op_at_fpr(0.10),
            "fpr<=0.15": _op_at_fpr(0.15),
        },
        "best_f1": max(pr_curve, key=lambda o: o["f1"]),
        "pr_curve": pr_curve,
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {OUT}")
    print(json.dumps({k: out[k] for k in
                      ["population", "auc_refuse_if_below", "operating_points_by_false_refusal_budget",
                       "best_f1", "mechanism_ceilings"]}, indent=2))
    print("subclass n:", {k: v["n"] for k, v in out["negative_subclasses"].items()})


if __name__ == "__main__":
    main()
