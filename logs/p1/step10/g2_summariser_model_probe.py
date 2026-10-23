#!/usr/bin/env python
"""§G2 pre-flight — calibrate the ACTUAL summariser (`openai/gpt-oss-20b`), not the Qwen extractor.

Why this exists
---------------
`community_summaries._default_llm` calls `src.core.llm.call_llm`, and `call_llm` posts
`cfg.openai_model` — which `.env` sets to **`openai/gpt-oss-20b`**. The graph build's concept
extraction uses a DIFFERENT model (`Qwen/Qwen3-VL-8B-Instruct`, `config.yaml:concept_extraction`).
The first version of this pre-flight measured the Qwen model's context (15,000 tokens) and sized the
§G2 batch budget from it — the wrong model. This probe measures the one the summariser really uses:

  * its `max_model_len` (from `/v1/models`),
  * chars/token on REAL physics chunk text (gpt-oss has its own tokenizer),
  * whether a 3-6 sentence summary actually comes back (it is a reasoning model, so the hidden
    trace competes with the answer for the output budget — §I23(c)),
  * the wall time at each prompt size, since §I23(c) measured it 3.2-3.6x slower than Qwen.

    unset PYTHONPATH && uv run python logs/p1/step10/g2_summariser_model_probe.py \
        --out logs/p1/step10/g2_summariser_model_probe.json
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
from src.pdf_ingestion.community_summaries import LEAF_PROMPT, SYSTEM_PROMPT  # noqa: E402


def models(base: str) -> dict:
    with urllib.request.urlopen(base + "/v1/models", timeout=30) as r:
        d = json.loads(r.read().decode())
    return {m["id"]: m.get("max_model_len") for m in d.get("data", [])}


def chat(base: str, model: str, prompt: str, max_tokens=None, timeout=1800) -> dict:
    payload = {"model": model, "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                                            {"role": "user", "content": prompt}],
               "temperature": 0.3, "top_p": 0.9}
    if max_tokens:
        payload["max_tokens"] = max_tokens
    req = urllib.request.Request(
        base + "/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        ch = (d.get("choices") or [{}])[0]
        content = (ch.get("message") or {}).get("content") or ""
        return {"status": 200, "seconds": round(time.time() - t, 1), "usage": d.get("usage"),
                "finish_reason": ch.get("finish_reason"), "content_chars": len(content),
                "content_head": content[:200]}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "seconds": round(time.time() - t, 1),
                "error": e.read().decode()[:300]}
    except Exception as e:  # noqa: BLE001
        return {"status": "ERR", "seconds": round(time.time() - t, 1), "error": repr(e)[:200]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://10.0.10.70:8000")
    ap.add_argument("--model", default=None, help="default: the resolved cfg.openai_model")
    ap.add_argument("--sizes", type=int, nargs="+", default=[20000, 60000, 273000])
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    cfg = get_settings()
    model = args.model or cfg.openai_model
    print(f"resolved summariser model: {model!r} (cfg.openai_model; base {cfg.openai_api_base})")
    print(f"gateway model context lengths: {json.dumps(models(args.base))}")

    with Session(get_engine(cfg)) as s:
        rows = s.exec(select(Chunk).limit(600)).all()  # type: ignore[attr-defined]
    blob = "\n\n---\n\n".join(c.text for c in rows if c.text)
    print(f"real physics chunk text: {len(rows)} chunks, {len(blob)} chars")

    results = []
    for n in args.sizes:
        prompt = LEAF_PROMPT.format(body=blob[:n])
        row = {"target_body_chars": n, "prompt_chars": len(prompt)}
        row.update(chat(args.base, model, prompt))
        if row.get("usage"):
            pt = row["usage"]["prompt_tokens"]
            row["prompt_tokens"] = pt
            row["chars_per_token"] = round(len(prompt) / pt, 3)
        print(json.dumps(row, ensure_ascii=False)[:400])
        results.append(row)

    out = {
        "resolved_model": model,
        "openai_api_base": cfg.openai_api_base,
        "max_model_len": models(args.base).get(model),
        "measured": results,
        "chars_per_token_min": min([r["chars_per_token"] for r in results
                                    if "chars_per_token" in r], default=None),
    }
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
