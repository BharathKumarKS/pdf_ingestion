#!/usr/bin/env python
"""Mutation proof for the S5 independent verifier — mutates COPIES of the artifact, never the real one.

Recipe (independent-verification skill, "when the verifier reads a WRITTEN artifact"): copy the
artifact and every file the verifier reads into a scratch directory, apply ONE targeted mutation per
check, run the verifier against the copy through `--base`, and record the full pass/fail vector.
Two properties, and they are different: (a) each mutation reddens its INTENDED check, and (b) EVERY
check is reddened by at least one mutation — no inert check.

Run:  python logs/p1/step10/lane_inclusion_verifier_mutation.py --artifact lane_inclusion_smoke4.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
BASE = REPO / "logs" / "p1" / "step10"
VERIFIER = BASE / "lane_inclusion_verifier.py"
READS = ("t0_baseline.json", "policy_confirm.json")


def _row(doc, qid):
    return next(r for r in doc["per_query"] if r["id"] == qid)


def mv_metric(doc):
    r = _row(doc, "ovw-001")
    r["F3_metrics"]["ndcg_at_20"] = round(r["F3_metrics"]["ndcg_at_20"] + 0.05, 4)


def mv_mrr(doc):
    r = _row(doc, "ovw-001")
    r["F1_metrics"]["mrr_at_20"] = round((r["F1_metrics"]["mrr_at_20"] or 0.0) + 0.05, 4)


def mv_endpoint_page(doc):
    """Remove the FIRST RELEVANT page from an arm's endpoint list.

    ⚠️ The first version of this mutation removed the LAST page, and it reddened NOTHING: the last
    page is usually irrelevant, so neither `mrr_at_20` (the first relevant page's rank) nor coverage
    (the intersection with the reachable-and-relevant set) can see it. A mutation must change the
    quantity the check READS, not merely the record.
    """
    r = _row(doc, "gold-003")
    rel = {int(p) for p in r["relevant_pages"]}
    keep = [p for p in r["F0_pages"] if int(p) not in rel] if r["F0_pages"][0] in rel else r["F0_pages"]
    if r["F0_pages"][0] in rel:
        r["F0_pages"] = r["F0_pages"][1:]
    else:
        r["F0_pages"] = keep


def mv_pool_page(doc):
    r = _row(doc, "ovw-002")
    r["F1_pool_pages"] = r["F1_pool_pages"][:-1]


def mv_aggregate(doc):
    doc["aggregate"]["F3"]["overall"]["ndcg_at_20"] += 0.05


def mv_delta(doc):
    doc["deltas"]["F3_minus_F0f"]["ndcg_at_20"]["mean"] += 0.05


def mv_guard(doc):
    doc["guards"]["G4_no_reranker_fallback_in_any_arm"] = True
    _row(doc, "gold-003")["F2_reranker_fallback"] = True


def mv_anchor(doc):
    """The verifier re-derives G2 from policy_confirm's pages — change THAT side."""
    doc["__pc_pages_flip__"] = True


def mv_g3(doc):
    r = _row(doc, "ovw-002")
    base = set(r["F0f_pool_pages"])
    r["F1_pool_pages"] = [p for p in r["F1_pool_pages"] if p not in base][:1]


def mv_pool_sha(doc):
    _row(doc, "ovw-002")["F2_pool_sha"] = "deadbeefdeadbeef"


def mv_n_queries(doc):
    doc["meta"]["n_queries"] = 999


def mv_slots_pageless(doc):
    r = _row(doc, "ovw-003")
    r["F3_slots"] = r["F3_slots"] + [None]


def mv_raptor_gate(doc):
    _row(doc, "gold-003")["F3_contrib"]["raptor"] = 2


MUTATIONS = [
    ("MV1 a row's ndcg_at_20 moved", mv_metric, {"V1"}),
    ("MV2 a row's mrr_at_20 moved", mv_mrr, {"V2"}),
    ("MV3 the first RELEVANT endpoint page removed", mv_endpoint_page, {"V2", "V3"}),
    ("MV4 a POOL page removed", mv_pool_page, {"V4", "V10"}),
    ("MV5 an aggregate moved", mv_aggregate, {"V5"}),
    ("MV6 a delta mean moved", mv_delta, {"V6"}),
    ("MV7 a guard flag flipped (with the row that contradicts it)", mv_guard, {"V7"}),
    ("MV8 the ANCHOR's other side moved", mv_anchor, {"V8"}),
    ("MV9 F1's pool loses F0f's pages", mv_g3, {"V9"}),
    ("MV10 a pool_sha changed", mv_pool_sha, {"V10"}),
    ("MV11 meta.n_queries changed", mv_n_queries, {"V11"}),
    ("MV12 a slot list gains a page-less entry", mv_slots_pageless, {"V12"}),
    ("MV13 the RAPTOR lane fires on a factual row", mv_raptor_gate, {"V13"}),
]


def run_verifier(scratch: Path, artifact: str) -> set[str]:
    p = subprocess.run([sys.executable, str(VERIFIER), "--check", "--artifact", artifact,
                        "--base", str(scratch)], capture_output=True, text=True)
    failed = set()
    for line in p.stdout.splitlines():
        if "[FAIL]" in line:
            failed.add(line.split("]")[1].split("—")[0].strip().split()[0])
    return failed


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", default="lane_inclusion.json")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        scratch = Path(td)
        for f in READS:
            shutil.copy(BASE / f, scratch / f)
        orig = json.loads((BASE / args.artifact).read_text())

        # baseline
        (scratch / args.artifact).write_text(json.dumps(orig, indent=2))
        base_failed = run_verifier(scratch, args.artifact)
        print(f"=== S5 verifier mutation proof — {args.artifact} ===")
        print(f"baseline: {'FAILED ' + str(sorted(base_failed)) if base_failed else 'all green'}")
        if base_failed:
            print("BASELINE IS NOT ALL-GREEN — fix that before proving mutations")
            return 2

        rows, ok = [], True
        for name, fn, must in MUTATIONS:
            doc = json.loads((BASE / args.artifact).read_text())
            fn(doc)
            (scratch / args.artifact).write_text(json.dumps(doc, indent=2))
            if name.startswith("MV8"):
                # the anchor's other side: perturb policy_confirm's page lists for one query
                pc = json.loads((REPO / "logs/p1/step10/policy_confirm.json").read_text())
                for r in pc["per_query"]:
                    if r["id"] == "gold-003" and "pages" in r:
                        r["pages"] = list(r["pages"][1:]) + [9999]
                (scratch / "policy_confirm.json").write_text(json.dumps(pc, indent=2))
            failed = run_verifier(scratch, args.artifact)
            if name.startswith("MV8"):
                shutil.copy(BASE / "policy_confirm.json", scratch / "policy_confirm.json")
            hit = bool(failed & must)
            ok = ok and hit
            rows.append((name, must, hit, sorted(failed)))
            print(f"  [{'ok' if hit else 'FAIL'}] {name}")
            print(f"        must redden {sorted(must)} -> reddened {sorted(failed) or '[]'}")

        all_red = {t for _, _, _, f in rows for t in f}
        expected = {"V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8", "V9", "V10", "V11", "V12", "V13"}
        inert = sorted(expected - all_red)
        print()
        print(f"checks reddened by at least one mutation: {sorted(all_red)}")
        print(f"inert checks: {inert or 'none'}")
        ok = ok and not inert
        print()
        print("ALL MUTATIONS DISCRIMINATE" if ok else "MUTATION PROOF FAILED")
        return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
