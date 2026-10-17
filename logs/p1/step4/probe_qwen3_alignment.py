"""Step 4 FIRST ACTION — the Qwen3 local-tokenizer vs cluster-token alignment probe.

Plan §Step 4: §2.1 verified local↔API token alignment for *jina* only; R2 selects
`Qwen/Qwen3-Embedding-0.6B`, for which only the response *shape* (1, 19, 1024) was checked.
Every mean-pooled child vector depends on that alignment, so it is verified here before the
module is written.

What the probe establishes:

  Q1 count     — the local tokenizer's token count vs the number of vectors the cluster
                 returns, per special-token setting. (Measured: the API appends exactly one
                 `<|endoftext|>` vector, so `add_special_tokens=True` is the matching count and
                 the extra vector is the LAST one.)
  Q2 offsets   — the local `offset_mapping` (plain, no special tokens) tiles the text, so a
                 character span translates into token indices.
  Q3 position  — is vector i the vector of token i? Two checks that do not assume the answer:
                 (a) causal-prefix invariance: for a causal LM the hidden state at position i
                     depends only on positions <= i, so appending text must leave the content
                     vectors bit-identical;
                 (b) token identity: replacing a single-token word changes vector k and nothing
                     before it, tying local index k to that word.
  Q4 truncation — a parent-sized input (parent_max_tokens=5000) is not silently truncated:
                 local content count == API vectors - 1.

Run:  uv run python logs/p1/step4/probe_qwen3_alignment.py
Writes logs/p1/step4/alignment.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import numpy as np

URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"
MODEL = "Qwen/Qwen3-Embedding-0.6B"
CACHE = str(Path(__file__).resolve().parents[3] / "data" / "models")
OUT = Path(__file__).resolve().parent / "alignment.json"


def api_token_matrix(client: httpx.Client, text: str) -> np.ndarray:
    r = client.post(
        URL,
        json={"model": MODEL, "input": [text], "return_token_embeddings": True},
        timeout=300,
    )
    r.raise_for_status()
    arr = np.asarray(r.json()["data"][0]["embedding"], dtype=np.float32)
    return arr[0] if arr.ndim == 3 else arr


def main() -> int:
    from transformers import AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL, cache_dir=CACHE)
    print(f"tokenizer: {type(tok).__name__} vocab={tok.vocab_size} "
          f"bos={tok.bos_token_id} eos={tok.eos_token_id}")

    texts = [
        "The cat sat on the mat.",
        "Energy E = \u00bdmv\u00b2 is conserved; the gradient \u2207T drives heat flow.",
        "This is the second law: heat flows spontaneously from hot to cold, never the reverse.",
        "In the chapter on thermodynamics we saw that entropy never decreases in an "
        "isolated system.",
    ]

    report: dict = {"model": MODEL, "url": URL, "checks": {}, "texts": []}
    with httpx.Client() as client:
        for text in texts:
            ids_special = tok(text)["input_ids"]
            ids_plain = tok(text, add_special_tokens=False)["input_ids"]
            extra = [i for i in ids_special if i not in ids_plain]
            mat = api_token_matrix(client, text)
            report["texts"].append(
                {
                    "text": text,
                    "len_chars": len(text),
                    "local_tokens_special": len(ids_special),
                    "local_tokens_plain": len(ids_plain),
                    "api_vectors": int(mat.shape[0]),
                    "api_dim": int(mat.shape[1]),
                    "extra_special_ids": extra,
                    "special_token_is_last": bool(ids_special[:-1] == ids_plain),
                }
            )
            print(f"  local(sp)={len(ids_special):3d} local(plain)={len(ids_plain):3d} "
                  f"api={mat.shape[0]:3d} extra={extra} last={ids_special[:-1] == ids_plain}"
                  f"  | {text[:44]!r}")

    # ── Q1 count agreement ────────────────────────────────────────────────────
    agree_plain = all(t["local_tokens_plain"] == t["api_vectors"] for t in report["texts"])
    agree_special = all(t["local_tokens_special"] == t["api_vectors"] for t in report["texts"])
    special_is_last = all(t["special_token_is_last"] for t in report["texts"])
    report["checks"]["Q1_count_agrees_plain"] = agree_plain
    report["checks"]["Q1_count_agrees_special"] = agree_special
    report["checks"]["Q1_special_token_is_trailing"] = special_is_last
    print(f"\nQ1 count: plain={agree_plain} special={agree_special} trailing={special_is_last}")

    # ── Q2 offsets tile the text (plain tokenization) ─────────────────────────
    t0 = texts[0]
    offs = tok(t0, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
    tiled = (
        offs[0][0] == 0
        and offs[-1][1] == len(t0)
        and all(offs[i][1] == offs[i + 1][0] for i in range(len(offs) - 1))
    )
    report["checks"]["Q2_offsets_tile"] = bool(tiled)
    print(f"Q2 offsets tile: {tiled}  (first={offs[0]} last={offs[-1]} n={len(offs)})")

    # ── Q3a causal-prefix invariance (content tokens only; API appends EOS) ───
    base = texts[2]
    ext = base + " Nothing above may change because of these trailing words."
    n_base_plain = len(tok(base, add_special_tokens=False)["input_ids"])
    with httpx.Client() as client:
        m_base = api_token_matrix(client, base)
        m_ext = api_token_matrix(client, ext)
    prefix_identical = bool(np.array_equal(m_base[:n_base_plain], m_ext[:n_base_plain]))
    max_delta = float(np.abs(m_base[:n_base_plain] - m_ext[:n_base_plain]).max())
    # The trailing EOS vector itself must move (it is a different position) — that is the
    # control showing the comparison is not vacuously true.
    eos_delta = float(np.abs(m_base[-1] - m_ext[n_base_plain]).max())
    report["checks"].update(
        {
            "Q3a_prefix_invariant": prefix_identical,
            "Q3a_max_abs_delta": max_delta,
            "Q3a_control_eos_delta": eos_delta,
            "Q3a_n_content_tokens": n_base_plain,
            "Q3a_api_vectors_base": int(m_base.shape[0]),
            "Q3a_api_vectors_ext": int(m_ext.shape[0]),
        }
    )
    print(f"Q3a prefix invariance: identical={prefix_identical} max|Δ|={max_delta:.3e} "
          f"(control: EOS-position Δ={eos_delta:.3e})")

    # ── Q3b token identity: one-token word swap, only its vector moves ────────
    a = "The cat sat quietly on the mat beside the door."
    b = "The dog sat quietly on the mat beside the door."
    ids_a = tok(a, add_special_tokens=False)["input_ids"]
    ids_b = tok(b, add_special_tokens=False)["input_ids"]
    toks_a = tok.convert_ids_to_tokens(ids_a)
    toks_b = tok.convert_ids_to_tokens(ids_b)
    diff_idx = [i for i in range(min(len(ids_a), len(ids_b))) if ids_a[i] != ids_b[i]]
    k = diff_idx[0] if diff_idx else -1
    same_len = len(ids_a) == len(ids_b)
    with httpx.Client() as client:
        ma = api_token_matrix(client, a)
        mb = api_token_matrix(client, b)
    # A causal LM attends backwards only: changing token k must leave positions < k
    # bit-identical (that is the alignment evidence) and MUST change positions >= k
    # (the control — if the tail were also unchanged, the comparison would be vacuous).
    before_identical = bool(np.array_equal(ma[:k], mb[:k])) if k > 0 else False
    after_identical = bool(np.array_equal(ma[k + 1 :], mb[k + 1 :]))
    at_k_delta = float(np.abs(ma[k] - mb[k]).max()) if k >= 0 else float("nan")
    report["checks"].update(
        {
            "Q3b_same_token_count": same_len,
            "Q3b_first_changed_index": k,
            "Q3b_changed_tokens": [toks_a[k], toks_b[k]] if k >= 0 else [],
            "Q3b_vectors_before_k_identical": before_identical,
            "Q3b_vectors_after_k_unchanged": after_identical,
            "Q3b_delta_at_k": at_k_delta,
        }
    )
    print(f"Q3b token identity: same_len={same_len} k={k} "
          f"({toks_a[k] if k >= 0 else '?'} -> {toks_b[k] if k >= 0 else '?'}) "
          f"before={before_identical} after={after_identical} max|Δ|@k={at_k_delta:.3e}")

    # ── Q4 no silent truncation at parent size ────────────────────────────────
    filler = "Entropy of the isolated system increases monotonically with time. "
    long_text = filler * 400  # ~ 5000+ tokens, i.e. at/over parent_max_tokens
    n_long_plain = len(tok(long_text, add_special_tokens=False)["input_ids"])
    with httpx.Client() as client:
        m_long = api_token_matrix(client, long_text)
    report["checks"].update(
        {
            "Q4_local_content_tokens": n_long_plain,
            "Q4_api_vectors": int(m_long.shape[0]),
            "Q4_no_truncation": int(m_long.shape[0]) == n_long_plain + 1,
        }
    )
    print(f"Q4 truncation: local content={n_long_plain} api={m_long.shape[0]} "
          f"no_truncation={int(m_long.shape[0]) == n_long_plain + 1}")

    aligned = bool(
        agree_special
        and special_is_last
        and tiled
        and prefix_identical
        and same_len
        and before_identical
        and (not after_identical)  # control: the tail must move
        and at_k_delta > 1.0
        and report["checks"]["Q4_no_truncation"]
    )
    report["verdict"] = {
        "aligned": aligned,
        "rule": "tokenize with add_special_tokens=False for offsets; the API matrix has exactly "
        "one extra TRAILING <|endoftext|> vector — drop it before span mapping",
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(f"\nverdict: aligned={aligned}\nrule: {report['verdict']['rule']}\nwrote {OUT}")
    return 0 if aligned else 1


if __name__ == "__main__":
    sys.exit(main())
