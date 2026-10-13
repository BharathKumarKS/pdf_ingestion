#!/usr/bin/env python3
"""Generate unanswerable / out-of-scope queries and VERIFY the book cannot answer them.

Three tiers (a good guardrail must handle all three; the third is what tests precision):
  out_of_domain    — not physics at all ("What is the capital of France?")
  in_domain_absent — physics, but this book does not cover it ("What does the book say
                     about the Schrödinger equation for the hydrogen atom?")
  near_miss        — adjacent to something the book DOES cover, but the specific fact is
                     absent. These are the valuable ones.

A candidate is accepted ONLY if a full two-pass scan finds no YES page. The scan runs over
a thread pool with a disk verdict cache (Task 4a), so a re-run is bit-identical.

Usage:
    uv run python scripts/generate_negatives.py --n 24 \\
        --pdf data/base_textbooks/feynman-lectures-on-physics-volume1.pdf \\
        --output data/eval_negatives.json

    # Probe three candidates first
    uv run python scripts/generate_negatives.py --n 3 --output /tmp/neg_probe.json

    # Wiring check only: no judge calls, no output written
    uv run python scripts/generate_negatives.py --dry-run
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_ROOT = Path(__file__).resolve().parents[1]

_SEEDS = {
    "out_of_domain": [
        "What is the capital of France?",
        "Who wrote Pride and Prejudice?",
        "What is the boiling point of mercury in Fahrenheit?",
        "What are the rules of cricket?",
        "How do you bake sourdough bread?",
        "What is the population of Tokyo?",
        "Which company makes the iPhone?",
        "What language is spoken in Brazil?",
        "What is the tallest mountain in the world?",
        "Who painted the Mona Lisa?",
        "How do you change a car tyre?",
        "What is the capital of Australia?",
    ],
    "in_domain_absent": [
        "What does the book say about the Schrödinger equation for the hydrogen atom?",
        "What is the book's treatment of general relativity and curved spacetime?",
        "What does the book say about the Higgs boson and electroweak symmetry breaking?",
        "What is the book's explanation of quantum entanglement and Bell's theorem?",
        "What does the book say about the Standard Model of particle physics?",
        "What is the book's derivation of the Navier-Stokes equations?",
        "What does the book say about superconductivity and the BCS theory?",
        "What is the book's treatment of the Fourier transform in signal processing?",
        "What does the book say about the quantum Hall effect?",
        "What is the book's treatment of the strong nuclear force?",
        "What does the book say about gravitational waves?",
        "What is the book's explanation of black hole thermodynamics?",
    ],
    "near_miss": [
        "What numerical value does the book give for the electron's magnetic moment?",
        "What does the book say the mass of the top quark is?",
        "Which year does the book state that the laser was invented?",
        "What does the book give as the half-life of carbon-14?",
        "What value does the book use for the cosmological constant?",
        "What does the book say the speed of sound in seawater is?",
        "What does the book list as the melting point of tungsten?",
        "How many moons does the book say Jupiter has?",
        "What value does the book give for the mass of the proton?",
        "What does the book state as the age of the universe?",
        "What does the book give as the boiling point of liquid nitrogen?",
        "Which year does the book give for the discovery of the neutron?",
    ],
}


def load_scanner():
    """Import validate_eval_calibration.py (it is a script, not a module)."""
    path = _ROOT / "scripts" / "validate_eval_calibration.py"
    spec = importlib.util.spec_from_file_location("vec_under_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load scanner from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    p = argparse.ArgumentParser(
        description="Generate unanswerable queries and verify the book cannot answer them")
    p.add_argument("--n", type=int, default=24)
    p.add_argument("--pdf", default="data/base_textbooks/feynman-lectures-on-physics-volume1.pdf")
    p.add_argument("--output", default="data/eval_negatives.json")
    p.add_argument("--dry-run", action="store_true",
                   help="List the candidates and the scan cost; no judge calls, no output")
    vec = load_scanner()
    vec.add_scan_args(p)
    vec.add_judge_args(p)
    args = p.parse_args()

    per_tier = max(1, args.n // len(_SEEDS))

    store = vec._get_page_store(args.pdf, args)
    coarse = len(range(max(args.page_start, 1), min(args.page_end, store.n_pages) + 1, args.scan_stride))

    if args.dry_run:
        print("DRY RUN — no judge calls, no output written")
        print(f"  pdf: {store.n_pages} pages; per candidate: {coarse} coarse + a dense pass "
              f"(±{args.scan_window})")
        print(f"  {per_tier} candidates per tier x {len(_SEEDS)} tiers = "
              f"{per_tier * len(_SEEDS)} candidates (~{per_tier * len(_SEEDS) * coarse} coarse calls)")
        for tier, seeds in _SEEDS.items():
            print(f"  {tier}:")
            for q in seeds[:per_tier]:
                print(f"    - {q}")
        return 0

    vec.resolve_judge(args)

    accepted, rejected = [], []
    per_tier_accepted: dict[str, int] = {}

    for tier, seeds in _SEEDS.items():
        taken = 0
        for q in seeds:
            if taken >= per_tier:
                break
            entry = {"id": f"neg-{tier[:3]}-{taken + 1:03d}", "query": q, "query_type": "factual"}
            try:
                hits = vec.scan_query(entry, args.pdf, args)
                yes = [h for h in hits if h["verdict"] == "YES"]
            except Exception as exc:
                print(f"  {q[:50]!r}: scan FAILED ({exc}) — skipped, not accepted")
                continue
            if yes:
                rejected.append((q, [h["page"] for h in yes]))
                print(f"  REJECT {q[:50]!r} — answered on {[h['page'] for h in yes][:4]}")
                continue
            accepted.append({
                "id": entry["id"],
                "query": q,
                "query_type": "factual",
                "answerable": False,
                "relevant_pages": [],
                "calibrated": True,
                "calibration_note": f"negative ({tier}); full scan found no YES page",
            })
            taken += 1
            per_tier_accepted[tier] = per_tier_accepted.get(tier, 0) + 1
            print(f"  ACCEPT {q[:50]!r}")

    Path(args.output).write_text(json.dumps(accepted, indent=2, ensure_ascii=False))
    print(f"\naccepted {len(accepted)}, rejected {len(rejected)} (answered by the book)")
    for tier in _SEEDS:
        print(f"  {tier}: accepted {per_tier_accepted.get(tier, 0)}/{per_tier}")
    print(f"wrote {args.output}")

    cache = vec._get_verdict_cache(args)
    if cache is not None:
        print(f"verdict cache: {cache.hits} hits / {cache.misses} misses -> {cache.path}")
    else:
        print("verdict cache: disabled (--no-cache)")

    # A wholly-rejected near_miss tier is a finding about the book's coverage, not a bug —
    # Feynman Vol 1 is comprehensive. But ZERO accepted overall means the scanner is broken.
    if not accepted:
        print("\n!! accepted 0 — the scanner is not working. Stop and debug.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
