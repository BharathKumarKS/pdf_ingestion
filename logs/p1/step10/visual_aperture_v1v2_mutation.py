#!/usr/bin/env python3
"""Mutation proof for the V1/V2 verifier. Every check must be REDDENED by >=1 mutation; no inert check.

Applies one mutation at a time to a COPY of the V1/V2 artifacts, runs the verifier on the copy, and
asserts the intended check FAILS. A check that no mutation can fail guards nothing.

Run:  .venv/bin/python logs/p1/step10/visual_aperture_v1v2_mutation.py
Exit 0 iff every mutation reddens its intended check and no check is inert.
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
V1 = ROOT / "logs/p1/step10/visual_aperture_v1.json"
V2 = ROOT / "logs/p1/step10/visual_aperture_v2.json"
VERIFIER = ROOT / "logs/p1/step10/visual_aperture_v1v2_verifier.py"
TMP = Path(tempfile.mkdtemp(prefix="v1v2_mut_"))


def _run(v1_obj, v2_obj) -> set[str]:
    p1 = TMP / "v1.json"; p2 = TMP / "v2.json"
    p1.write_text(json.dumps(v1_obj)); p2.write_text(json.dumps(v2_obj))
    r = subprocess.run([sys.executable, str(VERIFIER), str(p1), str(p2)],
                       capture_output=True, text=True)
    fails = set()
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("FAIL"):
            fails.add(line.split()[1])          # the check id, e.g. C3
    return fails


def main() -> int:
    base_v1 = json.loads(V1.read_text())
    base_v2 = json.loads(V2.read_text())

    # control: the unmutated artifacts pass
    ctrl = _run(base_v1, base_v2)
    print(f"control: fails={sorted(ctrl) or 'none'}  {'OK' if not ctrl else 'UNEXPECTED'}")

    muts: list = []

    def m_population(v1, v2):
        v1["rows"] = [r for r in v1["rows"] if not (r["modality"] == "text" and r["group"] == "vis_query")][:-1]
        return v1, v2
    muts.append(("M1 drop a text row", "C1", m_population))

    def m_error(v1, v2):
        v1.setdefault("errors", []).append({"label": "x", "error": "boom"})
        return v1, v2
    muts.append(("M2 inject an error", "C2", m_error))

    def m_threshold(v1, v2):
        for r in v1["rows"]:
            r["scores"] = [[p, max(0.9, c)] for p, c in r["scores"]]
        return v1, v2
    muts.append(("M3 all scores >= 0.58", "C3", m_threshold))

    def m_points(v1, v2):
        v1["meta"]["points_after"] = v1["meta"]["points_before"] + 1
        return v1, v2
    muts.append(("M4 point count moved", "C4", m_points))

    def m_patches(v1, v2):
        mi = next(r["n_query_patches"] for r in v1["rows"] if r["modality"] == "image")
        for r in v1["rows"]:
            if r["modality"] == "text":
                r["n_query_patches"] = mi
        return v1, v2
    muts.append(("M5 text patches == image", "C5", m_patches))

    def m_modality(v1, v2):
        for r in v1["rows"]:
            if r["modality"] == "text":
                r["modality"] = "image"
        return v1, v2
    muts.append(("M6 collapse modalities", "C6", m_modality))

    def m_top1(v1, v2):
        v2["per_row"][0]["top1"] += 0.01
        return v1, v2
    muts.append(("M7 perturb a top1", "C7", m_top1))

    def m_margin(v1, v2):
        v2["per_row"][1]["margin"] += 0.01
        return v1, v2
    muts.append(("M8 perturb a margin", "C8", m_margin))

    def m_z(v1, v2):
        v2["per_row"][2]["z"] += 0.01
        return v1, v2
    muts.append(("M9 perturb a z", "C9", m_z))

    def m_self(v1, v2):
        v2["meta"]["n_self_match"] += 1
        return v1, v2
    muts.append(("M10 self-match count off", "C10", m_self))

    def m_sep(v1, v2):
        s = v2["separation"]["image"]["stats"]["top1"]
        s["separating"] = not s["separating"]
        return v1, v2
    muts.append(("M11 flip image separation verdict", "C11", m_sep))

    ok = not ctrl
    for name, want, fn in muts:
        v1, v2 = fn(copy.deepcopy(base_v1), copy.deepcopy(base_v2))
        fails = _run(v1, v2)
        reddened = want in fails
        ok = ok and reddened
        print(f"  {'REDDEN' if reddened else 'INERT '}  {name}  -> intended {want}, fails={sorted(fails)}")

    print(f"\n{'ALL REDDENED, NO INERT' if ok else 'PROBLEM: an inert or mis-targeted mutation'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
