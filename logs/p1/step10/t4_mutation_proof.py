"""T4 mutation proof — is every check in the verifier able to FAIL, and is every check reachable?

Pre-registration §7: "each mutation must turn exactly its own check red, and EVERY check must be reddened by
at least one mutation (no inert check)."

Method: take the smoke artifact (a real artifact with the real schema, 8 queries), apply ONE mutation at a
time to a copy, run the real verifier on the mutated copy as a subprocess, and record which checks fired.
⚠️ A check that never fires under ANY mutation is inert, and an inert check is worse than no check.

Usage:  python logs/p1/step10/t4_mutation_proof.py
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path("logs/p1/step10/t4_smoke.json")
VERIFIER = "logs/p1/step10/t4_verifier.py"

# check tag -> the substring its failure line carries
CHECKS = {
    "CHECK_METRIC":     " != re-derived ",
    "CHECK_COVERAGE":   ".coverage: recorded",
    "CHECK_NREACHABLE": "n_reachable",
    "CHECK_AGG":        "aggregate.",
    "CHECK_G1":         "G1:",
    "CHECK_G2":         "G2:",
    "CHECK_G3":         "G3:",
    "CHECK_G4":         "G4:",
    "CHECK_G4B":        "G4b:",
    "CHECK_G5":         "G5:",
    "CHECK_G5B":        "G5b:",
    "CHECK_G6":         "G6:",
    "CHECK_G6B":        "G6b:",
    "CHECK_G7":         "G7:",
    "CHECK_G8":         "G8:",
    "CHECK_G9":         "G9:",
    "CHECK_G9B":        "G9b:",
    "CHECK_G10":        "G10:",
    "CHECK_I95":        "§I95",
    "CHECK_DELTA":      "deltas.",
}


def classify(line: str) -> set[str]:
    return {tag for tag, sub in CHECKS.items() if sub in line}


def first_query(art: dict) -> dict:
    return next(r for r in art["per_query"] if "error" not in r)


# ── the mutations: (name, fn(artifact) -> None, the check it is AIMED at) ─────────────────────────
def m_metric(a):
    first_query(a)["C_metrics"]["ndcg_at_20"] = 0.9999


def m_coverage(a):
    first_query(a)["N_cov"] = 0.9999


def m_n_reachable(a):
    first_query(a)["n_reachable"] = 12345


def m_aggregate(a):
    a["aggregate"]["W50"]["overall"]["map"] = 0.9999


def m_g1(a):
    a["aggregate"]["C"]["overall"]["ndcg_at_20"] = 0.9999


def m_g2(a):
    a["aggregate"]["N"]["overall"]["recall_at_100"] = 0.9999


def m_g3(a):
    a["errors"] = [{"id": "gold-003", "error": "injected"}]


def m_g4(a):
    first_query(a)["C2_pages"] = [999]


def m_g4b(a):
    """Only the RECORDED repeat metrics change — the pages are untouched, so G4 stays green."""
    m = first_query(a)["C2_metrics"]
    m["ndcg_at_20"] = 0.9999


def m_g5b(a):
    a["meta"]["override_hits"] = 0


def m_g6b(a):
    first_query(a)["N_pool_sha"] = "deadbeefdeadbeef"


def m_g8(a):
    a["meta"]["fetch_k"]["N"] = 50


def m_pool_cov(a):
    """The POOL coverage is a separate quantity from the endpoint coverage — it must be its own field."""
    first_query(a)["N_pool_cov"] = 0.9999


def m_g9(a):
    first_query(a)["N_colbert_drop"] = True


def m_g9b(a):
    first_query(a)["C2_colbert_drop"] = True


def m_g10(a):
    first_query(a)["C_reranker_fallback"] = True


def m_g5(a):
    for r in a["per_query"]:
        if "Q_pages" in r:
            r["Q_pages"] = list(r["C_pages"])          # make Q a copy of C — the silent-no-op failure


def m_g6(a):
    first_query(a)["N_pool_size"] = 999999


def m_g7(a):
    first_query(a)["n_reachable"] = 0                    # collides with T0's own n_reachable


def m_i95(a):
    a["aggregate"]["Q"]["overall"]["mrr"] = 0.9999       # breaks the pool-mrr identity


def m_delta(a):
    a["deltas"]["P1_N_minus_C"]["map"]["mean"] = 0.9999


def m_page_order(a):
    """Reorder arm C's endpoint pages — recall is unchanged, so ONLY the ordering metrics must move."""
    r = first_query(a)
    p = r["C_pages"]
    r["C_pages"] = p[::-1] if len(p) > 1 else p


MUTATIONS = [
    ("metric value",        m_metric,       "CHECK_METRIC"),
    ("coverage value",      m_coverage,     "CHECK_COVERAGE"),
    ("n_reachable",         m_n_reachable,  "CHECK_NREACHABLE"),
    ("aggregate mean",      m_aggregate,    "CHECK_AGG"),
    ("G1 anchor (arm C)",   m_g1,           "CHECK_G1"),
    ("G2 anchor (arm N)",   m_g2,           "CHECK_G2"),
    ("G3 error count",      m_g3,           "CHECK_G3"),
    ("G4 repeat",           m_g4,           "CHECK_G4"),
    ("G4b repeat METRICS",  m_g4b,          "CHECK_G4B"),
    ("G5 Q == C (no-op)",   m_g5,           "CHECK_G5"),
    ("G5b override count",  m_g5b,          "CHECK_G5B"),
    ("G6 pool size",        m_g6,           "CHECK_G6"),
    ("G6b pool CONTENT",    m_g6b,          "CHECK_G6B"),
    ("G7 reachable set",    m_g7,           "CHECK_G7"),
    ("G8 fetch_k",          m_g8,           "CHECK_G8"),
    ("G9 lane dropout",     m_g9,           "CHECK_G9"),
    ("G9b repeat dropout",  m_g9b,          "CHECK_G9B"),
    ("G10 reranker fallbk", m_g10,          "CHECK_G10"),
    ("pool_cov field",      m_pool_cov,     "CHECK_AGG"),
    ("§I95 pool mrr",       m_i95,          "CHECK_I95"),
    ("delta mean",          m_delta,        "CHECK_DELTA"),
    ("page ORDER only",     m_page_order,   "CHECK_METRIC"),
]


def main() -> int:
    base = json.loads(SRC.read_text())
    fired: dict[str, list[str]] = {tag: [] for tag in CHECKS}
    inert_mutations: list[str] = []
    print(f"mutation proof on {SRC} ({len(base['per_query'])} queries)\n")
    for name, fn, aimed in MUTATIONS:
        art = copy.deepcopy(base)
        fn(art)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(art, fh)
            tmp = fh.name
        out = subprocess.run([sys.executable, VERIFIER, "--art", tmp],
                             capture_output=True, text=True).stdout
        tags: set[str] = set()
        for line in out.splitlines():
            if line.strip().startswith("- "):
                tags |= classify(line)
        Path(tmp).unlink()
        if not tags:
            inert_mutations.append(name)
        for t in tags:
            fired[t].append(name)
        mark = "OK " if tags else "!! "
        print(f"  {mark}{name:22s} aimed {aimed:16s} -> fired {sorted(tags) if tags else 'NOTHING'}")

    print("\nper-check coverage:")
    uncovered = [t for t, v in fired.items() if not v]
    for t, v in fired.items():
        print(f"  {t:18s} {len(v):2d} mutation(s)  {v[:3]}")

    ok = not inert_mutations and not uncovered
    if inert_mutations:
        print(f"\n*** INERT MUTATIONS (fired nothing): {inert_mutations}")
    if uncovered:
        print(f"\n*** CHECKS NEVER REDDENED (inert checks): {uncovered}")
    print("\nMUTATION PROOF: every mutation fires and every check is reachable"
          if ok else "\nMUTATION PROOF: FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
