#!/usr/bin/env python
"""Mutation proof for lane-plan S3 — the lane selector on the eval path.

Each mutation puts back a DEFECT (the old semantics), not merely an old call site, runs the S3 test
file, and records which tests fail. Every mutation is a REPLACEMENT with a no-op or a wrong value,
never a deletion, so a failure is always on an ASSERTION and never on a syntax/collection error.
The source is restored byte-identically after each mutation and the sha256 is checked.

Run:  unset PYTHONPATH; uv run python -u logs/p1/step10/lane_inclusion_eval_mutation.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EVAL = REPO / "scripts" / "evaluate_rag.py"
STORE = REPO / "src" / "pdf_ingestion" / "store.py"
TESTS = "tests/test_lane_inclusion_eval.py"

# (name, file, old, new, the test this MUST redden)
MUTATIONS = [
    ("MV1 the fused branch is never taken (`if True`)", EVAL,
     "    if lanes is None:\n",
     "    if True:  # MUTATION\n",
     "test_fused_graph_arm_goes_through_the_fusion_not_the_append"),
    ("MV2 the RAPTOR gate is removed from the lane set", EVAL,
     '        lane_set = tuple(l for l in lanes if l != "raptor" or query_type == "overview")\n',
     "        lane_set = tuple(lanes)  # MUTATION\n",
     "test_raptor_gate_is_applied_to_the_lane_set_not_only_to_the_call"),
    ("MV3 the graph lane is given the fusion's vector, not the raw one", EVAL,
     "            graph_vector=q_vec,\n",
     "            graph_vector=search_vec,  # MUTATION\n",
     "test_fused_arm_passes_the_graph_lane_the_raw_query_vector"),
    ("MV4 the RAPTOR lane is never wired (raptor_vector=None)", EVAL,
     "            raptor_vector=search_vec,\n",
     "            raptor_vector=None,  # MUTATION\n",
     "test_raptor_hit_reaches_the_pool_through_the_fusion"),
    ("MV5 the control stops fabricating the graph score", EVAL,
     '                        gh.setdefault("score", 1.0)\n',
     "                        pass  # MUTATION\n",
     "test_default_lanes_none_uses_todays_wiring"),
    ("MV6 the control stops mapping graph page_num -> page_number", EVAL,
     '                            gh["page_number"] = gh.get("page_num")\n',
     "                            pass  # MUTATION\n",
     "test_default_lanes_none_uses_todays_wiring"),
    # ⚠️ MV7 is the defect the LIVE probe found on 2026-10-30: `search_raptor` returned payload keys
    # only, so `_rrf_merge` dropped every RAPTOR candidate and the lane contributed nothing. The
    # first version of the S3 tests could not see it, because their fixture handed the fusion a
    # `chunk_id` — a shape the real lane never produces.
    ("MV7 `search_raptor` drops the point id (the lane vanishes in the fusion)", STORE,
     '        return [{"score": h.score, "qdrant_point_id": str(h.id), **h.payload}\n'
     "                for h in response.points]\n",
     '        return [{"score": h.score, **h.payload}\n'
     "                for h in response.points]  # MUTATION\n",
     "test_the_real_search_raptor_returns_a_key_the_fusion_can_use"),
]


def run_tests() -> tuple[set[str], str]:
    p = subprocess.run([sys.executable, "-m", "pytest", TESTS, "-q", "--tb=no", "-rf", "-p",
                        "no:cacheprovider"], cwd=REPO, capture_output=True, text=True)
    failed = set()
    for line in p.stdout.splitlines():
        if line.startswith("FAILED "):
            node = line.split()[1]
            failed.add(node.split("::")[1].split("[")[0])
    return failed, p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""


def main() -> int:
    originals = {p: p.read_bytes() for p in (EVAL, STORE)}
    shas = {p: hashlib.sha256(b).hexdigest() for p, b in originals.items()}

    base_failed, base_last = run_tests()
    print(f"=== S3 mutation proof — {TESTS} ===")
    for p, s in shas.items():
        print(f"{p.relative_to(REPO)} sha256 {s}")
    print(f"baseline: {'FAILED ' + str(sorted(base_failed)) if base_failed else 'all green'} "
          f"[{base_last}]")
    if base_failed:
        print("BASELINE IS NOT GREEN — fix that before proving mutations")
        return 2

    rows, ok = [], True
    for name, path, old, new, must in MUTATIONS:
        text = originals[path].decode()
        assert text.count(old) == 1, f"anchor not unique for {name}: {text.count(old)}"
        path.write_text(text.replace(old, new, 1))
        try:
            failed, last = run_tests()
        finally:
            path.write_bytes(originals[path])
            assert hashlib.sha256(path.read_bytes()).hexdigest() == shas[path], "RESTORE FAILED"
        reddened = must in failed
        ok = ok and reddened and bool(failed)
        rows.append((name, must, reddened, sorted(failed)))
        print(f"  [{'ok' if reddened else 'FAIL'}] {name}")
        print(f"        must redden: {must} -> {'RED' if reddened else 'still green'}")
        print(f"        reddened: {sorted(failed) or '[]'}  [{last}]")

    all_red = {t for _, _, _, f in rows for t in f}
    print()
    print(f"tests reddened by at least one mutation: {sorted(all_red)}")
    intact = all(hashlib.sha256(p.read_bytes()).hexdigest() == shas[p] for p in originals)
    print("source restored byte-identical" if intact else "RESTORE MISMATCH")
    print()
    print("ALL MUTATIONS DISCRIMINATE" if ok else "MUTATION PROOF FAILED")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
