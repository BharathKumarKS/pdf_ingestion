#!/usr/bin/env python3
"""Mutation proof for the V3 set verifier. Every check must be reddened by >=1 mutation.

Runs `visual_aperture_v3_set.py --verify-only --manifest <mutated copy>` as a subprocess and
asserts (a) the unmutated manifest is GREEN, and (b) each mutation turns its target check RED.
A check that no mutation can redden guards nothing (the project's "no inert check" rule).
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "logs/p1/step10/visual_aperture_v3_set.json"
VERIFIER = ROOT / "logs/p1/step10/visual_aperture_v3_set.py"


def run(manifest_obj) -> tuple[int, str]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(manifest_obj, f)
        tmp = f.name
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    p = subprocess.run([sys.executable, str(VERIFIER), "--verify-only", "--manifest", tmp],
                       cwd=str(ROOT), env=env, capture_output=True, text=True)
    os.unlink(tmp)
    return p.returncode, p.stdout + p.stderr


def failed_ids(out: str) -> set[str]:
    ids = set()
    for ln in out.splitlines():
        if "  FAIL  " in ln:
            parts = ln.split()
            i = parts.index("FAIL")
            ids.add(parts[i + 1])
    return ids


def main() -> int:
    base = json.loads(MANIFEST.read_text())

    rc, out = run(base)
    print(f"control (unmutated): exit={rc} failed={sorted(failed_ids(out))}")
    ok = rc == 0 and not failed_ids(out)

    muts = []
    m = copy.deepcopy(base)                      # M1 — same image in both splits
    cal = next(i for i in m["images"] if i["split"] == "calibration")
    dup = dict(cal); dup["id"] = dup["id"] + "_dup"; dup["split"] = "heldout"
    m["images"].append(dup)
    muts.append(("M1 duplicate_image_into_both_splits", m, "R-3"))

    m = copy.deepcopy(base)                      # M2 — corrupt a content hash
    m["images"][0]["sha256"] = "deadbeefdeadbeef"
    muts.append(("M2 corrupt_sha256", m, "R-2"))

    m = copy.deepcopy(base)                      # M3 — point at a missing file
    m["images"][0]["file"] = "/nonexistent/zzz.png"
    muts.append(("M3 missing_file", m, "R-1"))

    m = copy.deepcopy(base)                      # M4 — empty the held-out half
    m["images"] = [i for i in m["images"] if i["split"] != "heldout"]
    muts.append(("M4 drop_heldout", m, "R-4"))

    m = copy.deepcopy(base)                      # M5 — strip provenance
    m["images"][0]["source"] = ""
    muts.append(("M5 blank_source", m, "R-5"))

    m = copy.deepcopy(base)                      # M6 — a non-Feynman item labelled in_domain
    in_dom = next(i for i in m["images"] if i["group"] == "in_domain")
    in_dom["source"] = "ck12_test_book"
    muts.append(("M6 in_domain_not_from_feynman", m, "R-6"))

    print()
    all_ok = ok
    for name, obj, target in muts:
        rc, out = run(obj)
        fired = target in failed_ids(out)
        print(f"{name:44s} target={target:4s} exit={rc} reddened={fired}")
        all_ok = all_ok and rc != 0 and fired

    print(f"\n{'ALL MUTATIONS REDDEN, NO INERT CHECK' if all_ok else 'MUTATION PROOF FAILED'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
