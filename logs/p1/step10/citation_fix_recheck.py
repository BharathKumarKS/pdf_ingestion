#!/usr/bin/env python3
"""§I115 — re-derive the citation metrics over the EXISTING `v3_judged_full` run, OLD vs NEW.

Read-only, no cluster. Proves the shipped metric saw nothing and reports the corrected numbers.

Run:  .venv/bin/python logs/p1/step10/citation_fix_recheck.py
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "data/eval_results/v3_judged_full_2026-11-03_0115.json"
OUT = ROOT / "logs/p1/step10/citation_fix.json"

OLD_RE = re.compile(r"\[Page (\d+)\]", re.I)              # the metric as SHIPPED (§I115)
NEW_RE = re.compile(r"[\[【(]\s*[Pp]age\s*(\d+)\s*[\]】)]")  # the fix: both brackets, any space


def _cited(rx: re.Pattern, answer: str) -> list[int]:
    return sorted({int(m) for m in rx.findall(answer or "")})


def main() -> None:
    data = json.loads(SRC.read_text())
    res = [r for r in data["results"] if r.get("answerable") is True]
    per = []
    for r in res:
        a = r.get("generation", {}).get("answer", "") or ""
        gold = set(r.get("relevant_pages") or [])
        ret = {c.get("page") for c in (r.get("top_chunks") or [])}
        co, cn = _cited(OLD_RE, a), _cited(NEW_RE, a)
        per.append({
            "id": r["id"], "n_gold": len(gold),
            "cited_old": co, "cited_new": cn,
            "valid_new": sorted(set(cn) & ret),
            "gold_hit_new": sorted(set(cn) & gold),
        })

    n = len(per)
    old_sees = sum(1 for x in per if x["cited_old"])
    new_sees = sum(1 for x in per if x["cited_new"])
    acc = [len(x["valid_new"]) / len(x["cited_new"]) for x in per if x["cited_new"]]
    ghr = [len(x["gold_hit_new"]) / x["n_gold"] for x in per if x["n_gold"]]

    agg = {
        "n_answers": n,
        "old_metric_sees_a_citation": old_sees,
        "old_metric_aggregate": 1.0 if old_sees == 0 else None,
        "new_cited": new_sees,
        "new_coverage": round(new_sees / n, 4),
        "new_uncited": n - new_sees,
        "new_uncited_share": round((n - new_sees) / n, 4),
        "new_accuracy_over_citing": round(st.mean(acc), 4) if acc else None,
        "new_answer_cites_gold_recall": round(st.mean(ghr), 4) if ghr else None,
    }
    artifact = {
        "meta": {
            "source": str(SRC.relative_to(ROOT)),
            "source_sha256": hashlib.sha256(SRC.read_bytes()).hexdigest(),
            "old_regex": OLD_RE.pattern, "new_regex": NEW_RE.pattern,
            "note": "read-only re-derivation; no run, no cluster, no store write",
        },
        "per_answer": per,
        "aggregates": agg,
    }
    OUT.write_text(json.dumps(artifact, indent=1))
    print(f"wrote {OUT}")
    print(json.dumps(agg, indent=1))


if __name__ == "__main__":
    main()
