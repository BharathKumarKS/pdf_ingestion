#!/usr/bin/env python
"""Re-runnable mutation proof for lane-plan S4 — `search_fused` (store.py).

The previous session recorded this proof as a LOG with no driver (`search_fused_mutation_log.txt`),
so it could not be re-run against a later revision of `store.py`. This is the driver: it puts each
defect BACK (the old semantics, not just a call site), runs `tests/test_search_fused.py`, and
records the full pass/fail vector. Every mutation is a REPLACEMENT with a no-op or a wrong value,
never a deletion, so a failure is always on an ASSERTION and never on a syntax/collection error.
`store.py` is restored byte-identically after each mutation and the sha256 is checked.

Run:  unset PYTHONPATH; uv run python -u logs/p1/step10/search_fused_mutation.py
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SRC = REPO / "src" / "pdf_ingestion" / "store.py"
TESTS = "tests/test_search_fused.py"

MUTATIONS = [
    ("MVA `_rrf_merge` ignores the per-lane weights",
     "                scores[cid] = scores.get(cid, 0.0) + w / (rrf_k + rank)\n",
     "                scores[cid] = scores.get(cid, 0.0) + 1.0 / (rrf_k + rank)  # MUTATION\n",
     "test_a_large_weight_promotes_that_lanes_candidates"),
    ("MVB a zero-weight lane is kept instead of removed",
     "        active = [(n, lst) for n, lst in contributors if w.get(n, 0.0) > 0]\n",
     "        active = [(n, lst) for n, lst in contributors]  # MUTATION\n",
     "test_zero_weight_removes_the_lane"),
    ("MVC the weight/lane length-mismatch guard is removed",
     "        if len(wts) != len(result_lists):\n"
     "            raise ValueError(\n"
     "                f\"weights has {len(wts)} entries but there are {len(result_lists)} lane lists\")\n",
     "        if False:  # MUTATION\n"
     "            raise ValueError(\"unreachable\")\n",
     "test_weights_length_mismatch_raises"),
    ("MVD `search_fused` APPENDS the lanes instead of fusing them",
     "            fused = self._rrf_merge(*[lst for _, lst in active], rrf_k=1,\n"
     "                                    weights=[w[n] for n, _ in active])\n",
     "            fused = [h for _, lst in active for h in lst]  # MUTATION\n",
     "test_every_candidate_carries_an_rrf_score"),
    ("MVE `_rrf_merge` ignores a candidate's RANK within its lane",
     "            for rank, item in enumerate(result_list, start=1):\n",
     "            for rank, item in enumerate(result_list, start=1):\n"
     "                rank = 1  # MUTATION\n",
     "test_rrf_score_decreases_with_rank_within_a_lane"),
    # ⚠️ MVE does NOT redden `test_fused_rank_depends_on_the_lane_rank`, and that is expected rather
    # than a gap in the mutation: making every score within a lane EQUAL leaves the ordering test
    # passing, because a stable sort preserves insertion order and reversing the lane changes the
    # insertion order. That test asserts on a DERIVED ordering, which can survive a change to the
    # score; the assertion that reads the score is the one MVE reddens. MVF below targets the
    # ordering test directly, with a defect that makes the order independent of the lane's rank.
    ("MVF `_rrf_merge` sorts by candidate id, not by fused score",
     "        for cid, rrf_score in sorted(scores.items(), key=lambda x: -x[1]):\n",
     "        for cid, rrf_score in sorted(scores.items(), key=lambda x: x[0]):  # MUTATION\n",
     "test_fused_rank_depends_on_the_lane_rank"),
]


def run_tests() -> tuple[set[str], str]:
    p = subprocess.run([sys.executable, "-m", "pytest", TESTS, "-q", "--tb=no", "-rf",
                        "-p", "no:cacheprovider"], cwd=REPO, capture_output=True, text=True)
    failed = set()
    for line in p.stdout.splitlines():
        if line.startswith("FAILED "):
            failed.add(line.split()[1].split("::")[1].split("[")[0])
    return failed, p.stdout.strip().splitlines()[-1] if p.stdout.strip() else ""


def main() -> int:
    original = SRC.read_bytes()
    sha0 = hashlib.sha256(original).hexdigest()
    text = original.decode()

    base_failed, base_last = run_tests()
    print(f"=== S4 mutation proof (search_fused) — {TESTS} ===")
    print(f"store.py sha256 {sha0}")
    print(f"baseline: {'FAILED ' + str(sorted(base_failed)) if base_failed else 'all green'} "
          f"[{base_last}]")
    if base_failed:
        print("BASELINE IS NOT GREEN — fix that before proving mutations")
        return 2

    rows, ok = [], True
    for name, old, new, must in MUTATIONS:
        assert text.count(old) == 1, f"anchor not unique for {name}: {text.count(old)}"
        SRC.write_text(text.replace(old, new, 1))
        try:
            failed, last = run_tests()
        finally:
            SRC.write_bytes(original)
            assert hashlib.sha256(SRC.read_bytes()).hexdigest() == sha0, "RESTORE FAILED"
        reddened = must in failed
        ok = ok and reddened and bool(failed)
        rows.append((name, must, reddened, sorted(failed)))
        print(f"  [{'ok' if reddened else 'FAIL'}] {name}")
        print(f"        must redden: {must} -> {'RED' if reddened else 'still green'}")
        print(f"        reddened: {sorted(failed) or '[]'}  [{last}]")

    all_red = {t for _, _, _, f in rows for t in f}
    print()
    print(f"tests reddened by at least one mutation: {sorted(all_red)}")
    print("source restored byte-identical" if hashlib.sha256(SRC.read_bytes()).hexdigest() == sha0
          else "RESTORE MISMATCH")
    print()
    print("ALL MUTATIONS DISCRIMINATE" if ok else "MUTATION PROOF FAILED")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
