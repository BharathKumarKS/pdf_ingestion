#!/usr/bin/env python
"""§G2 pre-flight — calibrate chars->tokens on REAL physics chunk text.

Why this exists
---------------
The served summariser `Qwen/Qwen3-VL-8B-Instruct` has **max_model_len = 15,000 tokens** (read from
`/v1/models`; a 120,000-char prompt is refused with HTTP 400). The §G2 leaf prompts run to 273,470
chars, so the builder must batch them — and the batch budget has to be expressed in something the
server enforces, which is TOKENS.

Repeated English filler measured **6.23 chars/token** (`ctx_probe.py`), but physics text carries
LaTeX, symbols and layout, which tokenise worse. Sizing batches off the filler ratio would produce
batches that still 400 on the real corpus. This probe measures the real ratio on real chunk text so
the budget in `community_summaries.DEFAULT_MAX_PROMPT_CHARS` is a measurement, not a guess.

    unset PYTHONPATH && uv run python logs/p1/step10/g2_token_ratio_probe.py \
        --out logs/p1/step10/g2_token_ratio.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlmodel import Session, select  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.database import Chunk, get_engine  # noqa: E402
from src.pdf_ingestion.community_summaries import LEAF_PROMPT  # noqa: E402

BASE = "http://10.0.10.70:8000"
MODEL = "Qwen/Qwen3-VL-8B-Instruct"


def chat(prompt: str) -> tuple:
    req = urllib.request.Request(
        BASE + "/v1/chat/completions",
        data=json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                         "max_tokens": 256, "temperature": 0}).encode(),
        headers={"Content-Type": "application/json"},
    )
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.loads(r.read().decode())
            return r.status, round(time.time() - t, 1), d.get("usage"), None
    except urllib.error.HTTPError as e:
        return e.code, round(time.time() - t, 1), None, e.read().decode()[:200]
    except Exception as e:  # noqa: BLE001
        return "ERR", round(time.time() - t, 1), None, repr(e)[:200]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[20000, 40000, 60000])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    cfg = get_settings()
    with Session(get_engine(cfg)) as s:
        rows = s.exec(select(Chunk).limit(400)).all()  # type: ignore[attr-defined]
    blob = "\n\n---\n\n".join(c.text for c in rows if c.text)
    print(f"real physics chunk text: {len(rows)} chunks, {len(blob)} chars")

    rows_out = []
    for n in args.sizes:
        prompt = LEAF_PROMPT.format(body=blob[:n])
        st, secs, usage, err = chat(prompt)
        row = {"target_body_chars": n, "prompt_chars": len(prompt), "status": st, "seconds": secs}
        if usage:
            row["prompt_tokens"] = usage["prompt_tokens"]
            row["chars_per_token"] = round(len(prompt) / usage["prompt_tokens"], 3)
            row["completion_tokens"] = usage["completion_tokens"]
            print(f"  {len(prompt):>7} prompt chars -> {usage['prompt_tokens']:>6} tokens "
                  f"= {row['chars_per_token']:.2f} chars/token ({secs}s)")
        else:
            row["error"] = err
            print(f"  {len(prompt):>7} prompt chars -> status {st}: {err!r}")
        rows_out.append(row)

    ratios = [r["chars_per_token"] for r in rows_out if "chars_per_token" in r]
    summary = {
        "model": MODEL,
        "endpoint": BASE,
        "max_model_len": 15000,
        "measured": rows_out,
        "chars_per_token_min": min(ratios) if ratios else None,
        "chars_per_token_max": max(ratios) if ratios else None,
        "conservative_chars_per_token_for_budgeting": min(ratios) if ratios else None,
        "note": "the batch budget uses the WORST (smallest) measured ratio, so a batch sized to fit "
                "fits for every sample measured",
    }
    print(json.dumps({k: v for k, v in summary.items() if k != "measured"}, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
