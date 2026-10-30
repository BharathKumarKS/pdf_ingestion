"""T4 independent review — a SECOND MODEL FAMILY reads the pre-registration and the harness's guard logic
and tries to break them.

Registered method (T4 pre-registration §7, and §I90's lesson): "an independent cross-family reviewer
(openai/gpt-oss-20b, read-only) on a COMPACT EXTRACT, never the full artifact."

Why a different family: the author of the pre-registration and the author of its checks are the same
reasoner, so the checks inherit its blind spots. Two convention traps already slipped through in this run
(§11 wrong, and the product's pool `mrr`); both were found by measurement, not by review. This is the
attempt to find the next one by reading.

Read-only. Writes nothing but its own log.

Usage:  python logs/p1/step10/t4_independent_review.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

PREREG = Path(".hermes/plans/2026-10-27-p1-endpoint-attribution-preregistration.md")
HARNESS = Path("logs/p1/step10/t4_endpoint.py")
LOG = Path("logs/p1/step10/t4_independent_review_log.txt")
ROUTER = os.environ.get("REVIEW_BASE", "http://10.0.10.70:8000/v1")
MODEL = os.environ.get("REVIEW_MODEL", "openai/gpt-oss-20b")

SYSTEM = """You are an adversarial methods reviewer for an empirical IR evaluation. You are given a
pre-registration document and the guard logic of its harness. Your job is to find things that are WRONG,
not to summarise. Be specific and terse.

Look especially for:
1. A guard that CANNOT FAIL, or that fails on correct data (over-strict).
2. A metric or field that does not measure what the document claims it measures.
3. Two arms that are not actually different (so the comparison is a no-op), or a "treatment" that is
   confounded with something else.
4. A registered prediction that the harness as described cannot falsify.
5. A denominator, unit, or convention that differs between what is described and what is computed.
6. Anything the document claims is measured that is in fact not measured.

Output: a numbered list. For each, give (a) the exact claim or code path, (b) why it is wrong, (c) the
consequence. If you find nothing in a category, do not invent something. End with a one-line verdict:
SOUND, or SPECIFIC CONCERNS."""


def main() -> int:
    prereg = PREREG.read_text()
    harness = HARNESS.read_text()
    # compact extract: the whole pre-registration, plus only the guard/delta/arm sections of the harness
    h_lines = harness.splitlines()
    keep, on = [], False
    for ln in h_lines:
        if any(k in ln for k in ("ARMS = {", "ENDPOINT_KEYS", "G1_KEYS", "def _endpoint_mrr",
                                 "def _cov", "_mkeys", "guards = {", "P_KEYS", "def delta")):
            on = True
        if on:
            keep.append(ln)
        if on and ln.startswith("}") and keep and len(keep) > 3:
            on = False
    user = (
        "=== PRE-REGISTRATION (verbatim) ===\n" + prereg +
        "\n\n=== HARNESS: arms, guards, deltas (extract) ===\n" + "\n".join(keep) +
        "\n\n=== CONTEXT YOU NEED ===\n"
        "T0 is a prior measurement whose artifact is the anchor. T0's `ce` row scores the cross-encoder's "
        "20-page list alone (so its R@100 equals its R@20). T0's `fusion` row scores the pool for `hits` and "
        "the pool's top-20 for `reranked` (so its `mrr` and R@100 are POOL metrics). The product's "
        "`compute_retrieval_metrics` computes `mrr` from retrieval['hits'] (the pool) and the rest from "
        "retrieval['reranked'] (the endpoint). Coverage is per query: |pages ∩ (rel ∩ reach)| / |rel ∩ reach|."
    )

    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        "temperature": 0.2,
        # ⚠️ gpt-oss is a REASONING model: its thinking is billed against max_tokens and lands in
        # `reasoning_content`. At 3000 the whole budget went to thinking and `content` came back None.
        "max_tokens": 20000,
    }).encode()
    req = urllib.request.Request(f"{ROUTER}/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    print(f"reviewer: {MODEL} at {ROUTER}")
    print(f"prompt: {len(user)} chars (pre-registration {len(prereg)}, harness extract {sum(len(l) for l in keep)})")
    try:
        with urllib.request.urlopen(req, timeout=900) as resp:
            data = json.loads(resp.read())
        ch = data["choices"][0]
        msg = ch["message"]
        out = msg.get("content") or ""
        if not out.strip():     # a truncated reasoning model leaves `content` empty
            out = "(content empty — finish_reason=" + str(ch.get("finish_reason")) + ")\n\n" + \
                  (msg.get("reasoning_content") or msg.get("reasoning") or "(no reasoning either)")
        print(f"finish_reason={ch.get('finish_reason')}  usage={data.get('usage')}")
    except Exception as exc:  # noqa: BLE001
        print(f"REVIEWER UNAVAILABLE: {type(exc).__name__}: {exc}")
        return 2
    LOG.write_text(f"reviewer: {MODEL}\n\n{out}\n")
    print("\n" + "=" * 78 + "\n" + out + "\n" + "=" * 78)
    print(f"\nlogged to {LOG}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
