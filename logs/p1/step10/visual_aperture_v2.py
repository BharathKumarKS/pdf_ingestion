#!/usr/bin/env python3
"""V2 — derive top1 / margin / z per query and the per-modality SEPARATION verdict. READ-ONLY.

Reads the V1 artifact (`logs/p1/step10/visual_aperture_v1.json`) and re-derives, from its RAW score
arrays, every statistic and the separation verdicts. No model, no store, no cluster.

Pre-registration: `.hermes/plans/2026-11-06-p1-visual-lane-aperture-V1V2-preregistration.md` §5.

  top1   = s[0]
  margin = s[0] - s[1]
  z      = (s[0] - mean(s)) / pstdev(s)

Separation (per statistic S, per modality M):  S separates iff min_S(IN) > max_S(OUT),
IN = in-domain groups, OUT = near ∪ far groups. Text has NO OUT group (V3's job) ⇒ its verdict is
`bounded_no_out_group` (a recorded limitation, not a pass).

Run:  .venv/bin/python logs/p1/step10/visual_aperture_v2.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

V1 = Path("logs/p1/step10/visual_aperture_v1.json")
OUT = Path("logs/p1/step10/visual_aperture_v2.json")

STATS = ("top1", "margin", "z")
IN_GROUPS = {"image": ["in_book_page", "in_concept"], "text": ["in_concept_text", "vis_query"]}
OUT_GROUPS = {"image": ["near_domain", "far_domain"], "text": []}


def _stats(scores: list[list]) -> dict:
    cos = [c for _p, c in scores]
    top1 = cos[0] if cos else 0.0
    top2 = cos[1] if len(cos) > 1 else 0.0
    mean = statistics.fmean(cos) if cos else 0.0
    sd = statistics.pstdev(cos) if len(cos) > 1 else 0.0
    return {"top1": top1, "top2": top2, "margin": top1 - top2,
            "mean": mean, "sd": sd, "z": ((top1 - mean) / sd if sd > 0 else 0.0),
            "n_scores": len(cos)}


def main() -> int:
    art = json.loads(V1.read_text())
    rows = art["rows"]

    per_row = []
    for r in rows:
        st = _stats(r["scores"])
        per_row.append({"modality": r["modality"], "group": r["group"], "label": r["label"],
                        "n_query_patches": r["n_query_patches"], **st})

    # self-match question (settled here): in_book_page top-1 is its OWN page at cosine 1.0?
    self_match = []
    for r in rows:
        if r["modality"] == "image" and r["group"] == "in_book_page":
            top = r["scores"][0] if r["scores"] else [None, 0.0]
            self_match.append({"label": r["label"], "expected_page": r.get("expected_page"),
                               "top1_page": top[0], "top1_cos": top[1],
                               "is_self_match": (top[0] == r.get("expected_page") and top[1] >= 0.9999)})

    separation = {}
    for modality in ("image", "text"):
        in_g = IN_GROUPS[modality]
        out_g = OUT_GROUPS[modality]
        in_rows = [x for x in per_row if x["modality"] == modality and x["group"] in in_g]
        out_rows = [x for x in per_row if x["modality"] == modality and x["group"] in out_g]
        block = {}
        for s in STATS:
            if not in_rows or not out_rows:
                block[s] = {"separating": False, "verdict": "bounded_no_out_group",
                            "min_in": min((x[s] for x in in_rows), default=None),
                            "max_out": None, "gap": None}
            else:
                mn = min(x[s] for x in in_rows)
                mx = max(x[s] for x in out_rows)
                block[s] = {"separating": mn > mx, "verdict": ("separates" if mn > mx else "no-separation"),
                            "min_in": mn, "max_out": mx, "gap": mn - mx}
        separation[modality] = {"n_in": len(in_rows), "n_out": len(out_rows), "stats": block}

    artifact = {
        "meta": {"source": str(V1), "n_rows": len(rows),
                 "n_self_match": sum(1 for s in self_match if s["is_self_match"]),
                 "n_self_match_checked": len(self_match)},
        "self_match": self_match,
        "per_row": per_row,
        "separation": separation,
    }
    OUT.write_text(json.dumps(artifact, indent=1))

    print(f"rows={len(rows)}  self-match: {artifact['meta']['n_self_match']}/{len(self_match)}")
    for modality, b in separation.items():
        print(f"\n[{modality}]  n_in={b['n_in']} n_out={b['n_out']}")
        for s in STATS:
            r = b["stats"][s]
            if r["max_out"] is None:
                print(f"  {s:7s} {r['verdict']}  (min_in={r['min_in']:.4f})" if r["min_in"] is not None
                      else f"  {s:7s} {r['verdict']}")
            else:
                print(f"  {s:7s} {r['verdict']:14s} min_in={r['min_in']:.4f} max_out={r['max_out']:.4f} "
                      f"gap={r['gap']:+.4f}")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
