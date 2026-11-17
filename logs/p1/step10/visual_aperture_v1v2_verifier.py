#!/usr/bin/env python3
"""DETERMINISTIC verifier for the visual-lane aperture V1 (capture) + V2 (statistics).

STDLIB ONLY, no model. Re-derives every reported cell from the RAW per-item score arrays in the V1
artifact, and every separation verdict, with an INDEPENDENT implementation (manual sums, not the
harness's `statistics` calls), then compares against what V2 recorded. Its own evaluation is
reproducible and needs no judge.

Run:  .venv/bin/python logs/p1/step10/visual_aperture_v1v2_verifier.py
Exit 0 iff every check passes.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

V1 = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("logs/p1/step10/visual_aperture_v1.json")
V2 = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("logs/p1/step10/visual_aperture_v2.json")
DEFAULT_THRESHOLD = 0.58
IN_GROUPS = {"image": {"in_book_page", "in_concept"}, "text": {"in_concept_text", "vis_query"}}
OUT_GROUPS = {"image": {"near_domain", "far_domain"}, "text": set()}
EPS = 1e-9


def _recompute(scores: list[list]) -> dict:
    """Independent top1/margin/z over a raw [[page, cos], ...] list."""
    cos = [c for _p, c in scores]
    n = len(cos)
    if n == 0:
        return {"top1": 0.0, "margin": 0.0, "z": 0.0}
    top1 = cos[0]
    top2 = cos[1] if n > 1 else 0.0
    mean = sum(cos) / n
    var = sum((c - mean) ** 2 for c in cos) / n if n > 1 else 0.0
    sd = math.sqrt(var)
    return {"top1": top1, "margin": top1 - top2, "z": ((top1 - mean) / sd if sd > 0 else 0.0)}


def main() -> int:
    v1 = json.loads(V1.read_text())
    v2 = json.loads(V2.read_text())
    rows = v1["rows"]
    per_row = v2["per_row"]
    checks: list[tuple[str, bool, str]] = []

    img = [r for r in rows if r["modality"] == "image"]
    txt = [r for r in rows if r["modality"] == "text"]
    meta = v1["meta"]

    # ── V1 guards ────────────────────────────────────────────────────────
    checks.append(("C1 G1 population (image>0, text==41)", len(img) > 0 and len(txt) == 41,
                   f"image={len(img)} text={len(txt)}"))
    checks.append(("C2 G2 zero errors", len(v1.get("errors", [])) == 0,
                   f"errors={len(v1.get('errors', []))}"))
    below = [r for r in rows if any(c < DEFAULT_THRESHOLD for _p, c in r["scores"])]
    checks.append(("C3 G3 threshold-0 honoured", all(len(r["scores"]) > 0 for r in rows)
                   and len(below) == len(rows), f"non-empty+below0.58={len(below)}/{len(rows)}"))
    checks.append(("C4 G4 read-only point count", meta.get("points_before") is not None
                   and meta.get("points_before") == meta.get("points_after"),
                   f"before={meta.get('points_before')} after={meta.get('points_after')}"))
    def _med(v):
        v = sorted(v); return v[len(v)//2] if v else 0
    mi, mt = _med([r["n_query_patches"] for r in img]), _med([r["n_query_patches"] for r in txt])
    checks.append(("C5 G5 patch counts differ", mi != mt and all(r["n_query_patches"] > 0 for r in rows),
                   f"median image={mi} text={mt}"))
    checks.append(("C6 G6 two modalities separate", len(img) > 0 and len(txt) > 0,
                   f"image={len(img)} text={len(txt)}"))

    # ── V2 statistics re-derived independently ───────────────────────────
    mism_top1 = mism_margin = mism_z = 0
    for r, pr in zip(rows, per_row):
        exp = _recompute(r["scores"])
        if abs(exp["top1"] - pr["top1"]) > EPS:
            mism_top1 += 1
        if abs(exp["margin"] - pr["margin"]) > EPS:
            mism_margin += 1
        if abs(exp["z"] - pr["z"]) > EPS:
            mism_z += 1
    checks.append(("C7 top1 re-derived", mism_top1 == 0, f"mismatches={mism_top1}/{len(rows)}"))
    checks.append(("C8 margin re-derived", mism_margin == 0, f"mismatches={mism_margin}/{len(rows)}"))
    checks.append(("C9 z re-derived", mism_z == 0, f"mismatches={mism_z}/{len(rows)}"))

    # self-match count re-derived
    n_self = 0
    for r in rows:
        if r["modality"] == "image" and r["group"] == "in_book_page":
            top = r["scores"][0] if r["scores"] else [None, 0.0]
            if top[0] == r.get("expected_page") and top[1] >= 0.9999:
                n_self += 1
    checks.append(("C10 self-match count re-derived",
                   n_self == v2["meta"]["n_self_match"],
                   f"re-derived={n_self} recorded={v2['meta']['n_self_match']}"))

    # separation verdicts re-derived
    sep_ok = True
    detail = []
    for modality in ("image", "text"):
        in_r = [r for r in per_row if r["modality"] == modality and r["group"] in IN_GROUPS[modality]]
        out_r = [r for r in per_row if r["modality"] == modality and r["group"] in OUT_GROUPS[modality]]
        for s in ("top1", "margin", "z"):
            rec = v2["separation"][modality]["stats"][s]
            if not in_r or not out_r:
                ok = (rec["verdict"] == "bounded_no_out_group" and rec["separating"] is False)
            else:
                mn = min(x[s] for x in in_r); mx = max(x[s] for x in out_r)
                ok = (rec["separating"] == (mn > mx)
                      and abs(rec["min_in"] - mn) <= EPS and abs(rec["max_out"] - mx) <= EPS
                      and abs(rec["gap"] - (mn - mx)) <= EPS)
            sep_ok = sep_ok and ok
            detail.append(f"{modality}/{s}:{'ok' if ok else 'BAD'}")
    checks.append(("C11 separation verdicts re-derived", sep_ok, " ".join(detail)))

    # ── report ───────────────────────────────────────────────────────────
    print(f"V1 rows={len(rows)}  V2 rows={len(per_row)}")
    n_pass = 0
    for name, ok, info in checks:
        print(f"  {'PASS' if ok else 'FAIL'}  {name}  [{info}]")
        n_pass += ok
    print(f"\n{n_pass}/{len(checks)} checks PASS")
    return 0 if n_pass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
