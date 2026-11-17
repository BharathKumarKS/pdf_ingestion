#!/usr/bin/env python3
"""Independent cross-family review of the session-39 parallel streams (read-only).

Asks a DIFFERENT model family (openai/gpt-oss-20b on the cluster router, vs the author's deepseek)
to CONFIRM or REFUTE each numbered claim by RE-DERIVING it from the attached raw evidence — not by
agreeing. Writes logs/p1/step10/session39_review.json.

    unset PYTHONPATH && .venv/bin/python logs/p1/step10/session39_review.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "logs/p1/step10/session39_review.json"
ROUTER = "http://10.0.10.70:8000/v1/chat/completions"
MODEL = "openai/gpt-oss-20b"


def _run(rel: str) -> str:
    r = subprocess.run([sys.executable, str(ROOT / rel)], capture_output=True, text=True,
                       cwd=str(ROOT))
    return r.stdout.strip() or r.stderr.strip()


def _shell(cmd: str) -> str:
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=str(ROOT))
    return (r.stdout + r.stderr).strip()


CLAIMS = """\
S1-V1. The V1 capture artifact reports 70 rows (29 image, 41 text), 0 errors, and a score range
       [0.1888, 1.0000] with 70/70 rows holding at least one score below 0.58 (threshold 0 honoured).
S1-V2. The median query patch count is 1031 (image) vs 37 (text) — the two modalities sit on
       different score scales (the patch-count normalisation).
S1-V3. For the IMAGE modality, ALL THREE statistics fail to separate in-domain from near/far:
       top1 min_in=0.4936 < max_out=0.5609 (gap -0.0673); margin min_in=0.0022 < max_out=0.0499
       (gap -0.0477); z min_in=3.8003 < max_out=5.7499 (gap -1.9496). I.e. no threshold separates.
S1-V4. All 12 in_book_page image probes are SELF-matches (top-1 is the query's own page at cosine
       1.0000), so that group is a self-match test, not a cross-render proof.
S1-V5. The deterministic verifier (independent arithmetic) passes 11/11, and the mutation proof
       reddens 11/11 mutations with NO inert mutation.
S3-A1. The local SPLADE (fastembed, prithivida/Splade_PP_en_v1) loads and encodes a query to a
       sparse vector (20 non-zeros).
S3-A2. The local sparse lane queries the REAL knowledge_base_v3 index and returns hits (5 hits,
       top score 22.0035) — the drop-in claim (no re-ingest).
S3-A3. The local cross-encoder (BAAI/bge-reranker-v2-m3) orders the RELEVANT passage above the
       irrelevant one (returned order = [2, 1] where page 2 is the relevant passage).
S3-A4. The original A4 check asserted a 'ce_score' key the reranker never emits (inert by
       construction) and was rewritten to assert the CE actually scored the real pool; it now
       reports A4_scores_n=30, A4_score_spread=0.9838, and passes.
S2-D1. data/guardrail_eval.jsonl holds 51 rows: 12 off_domain (expected block, stage domain) +
       22 benign_in_domain (expected pass) + 17 authored adversarial/benign-edge rows.
S2-D2. scripts/validate_guardrail_eval.py is a deterministic stdlib validator that exits 0 on the
       shipped file, and tests/test_guardrail_eval_dataset.py passes.
"""

INSTRUCTIONS = """\
You are a meticulous, INDEPENDENT reviewer. You did NOT produce this work. For EACH numbered claim,
decide CONFIRMED or REFUTED by re-deriving it from the attached RAW EVIDENCE (the actual verifier,
mutation, and probe outputs). Do NOT confirm from the claim's wording alone. If the evidence does
not let you re-derive a claim, say REFUTED with reason 'cannot re-derive'. Output STRICT JSON:
{"claims": [{"id": "...", "verdict": "CONFIRMED"|"REFUTED", "reason": "<=20 words"}]}.
"""


def main() -> int:
    evidence = {
        "V1V2_verifier_output": _run("logs/p1/step10/visual_aperture_v1v2_verifier.py"),
        "V1V2_mutation_output": _run("logs/p1/step10/visual_aperture_v1v2_mutation.py"),
        "V2_stats": json.loads((ROOT / "logs/p1/step10/visual_aperture_v2.json").read_text())["separation"],
        "V1_meta": json.loads((ROOT / "logs/p1/step10/visual_aperture_v1.json").read_text())["meta"],
        "probe_json": json.loads((ROOT / "logs/p1/step10/local_lane_fallback_probe.json").read_text()),
        "dataset_category_counts": _count_categories(),
        "validator_output": _shell(".venv/bin/python scripts/validate_guardrail_eval.py data/guardrail_eval.jsonl"),
        "pytest_output": _shell(".venv/bin/python -m pytest -q tests/test_guardrail_eval_dataset.py 2>&1 | tail -3"),
    }
    body = json.dumps({
        "model": MODEL, "temperature": 0,
        "messages": [
            {"role": "system", "content": INSTRUCTIONS},
            {"role": "user", "content": "CLAIMS:\n" + CLAIMS + "\n\nRAW EVIDENCE (JSON):\n"
             + json.dumps(evidence, indent=1, default=str)[:24000]},
        ],
    }).encode()
    req = urllib.request.Request(ROUTER, data=body, headers={"Content-Type": "application/json"})
    resp = json.loads(urllib.request.urlopen(req, timeout=300).read())
    content = resp["choices"][0]["message"]["content"]
    OUT.write_text(json.dumps({"model": MODEL, "raw": content}, indent=1))
    print(content)
    print(f"\nwrote {OUT}")
    return 0


def _count_categories() -> dict:
    from collections import Counter
    rows = [json.loads(l) for l in (ROOT / "data/guardrail_eval.jsonl").read_text().splitlines() if l.strip()]
    return {"n": len(rows), "by_category": dict(Counter(r["category"] for r in rows)),
            "by_expected": dict(Counter(r["expected"] for r in rows))}


if __name__ == "__main__":
    sys.exit(main())
