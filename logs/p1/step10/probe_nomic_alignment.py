#!/usr/bin/env python
"""Probe the endpoint's special-token layout, and its determinism, for the adopted dense model.

Why this exists
---------------
`LateChunkEmbedder` mean-pools an endpoint's **per-token** vectors over the character spans a local
tokenizer produced. That design rests on "local token *i* is API vector *i*", which is a property of
one tokenizer + one server — so it must be probed for the model actually in use, not inherited.

The Qwen3 contract was probed 2026-10-17 (`logs/p1/step4/probe_qwen3_alignment.py`): **one extra
TRAILING** vector, `n_api == n_local + 1`. §I77's addendum measured nomic at `n_api == n_local + 2`
— the same *delta* as gemma — but ⚠️ **which two tokens they are was NOT established**. For a
BERT-style tokenizer the obvious answer is `[CLS] ... [SEP]` (one LEADING, one trailing), and getting
that wrong is not an off-by-one on a count: it shifts every child's pooling window by one token,
silently.

Method — decides it without assuming anything about the model
-------------------------------------------------------------
Two calls, on one text and the same text plus a sentinel word. Left-to-right tokenization makes the
first text's content tokens a **prefix** of the second's, so the two responses align at the number of
LEADING special vectors:

    t1 = text               -> M1, n1 content tokens
    t2 = text + " sentinel" -> M2, n2 content tokens
    leading  = argmin_o  max|M1[o:o+n1] - M2[o:o+n1]|
    trailing = len(M1) - n1 - leading

RESULT (2026-10-25, `probe_nomic_alignment.json`)
-------------------------------------------------
    nomic  BertTokenizerFast  n_api == n_local + 2  ->  0 LEADING, 2 TRAILING  (matrix[:-2])
    Qwen3  Qwen2TokenizerFast n_api == n_local + 1  ->  0 LEADING, 1 TRAILING  (matrix[:-1])

⚠️ The BERT-style guess in the paragraph above — `[CLS] … [SEP]`, one LEADING — is **wrong for
nomic**: both extra vectors sit at the END. `matrix[:-1]` would therefore keep one special vector
and shift every child's pooling window, silently. nomic is declared `(0, 2)` in
`late_chunk_embedder._DECLARED_SPECIALS`.

⚠️ An earlier run of this probe reported nomic's per-token path as *not bit-reproducible*, and that
was an artefact of a bug in this script, not a property of the endpoint. Measured: **both paths ARE
bit-reproducible** (two identical calls differ by `max_abs_diff == 0.0`, 0 rows differing, for both
models). The alignment is nevertheless decided by the runner-up MARGIN rather than by an exact zero,
because the right offset is exactly 0 only for a CAUSAL model: Qwen3 matches at 0.0, while nomic is
bidirectional — appending the sentinel moves its earlier tokens' hidden states — and lands at 1.179
against 9.280 for the runner-up (**7.87x**). Qwen3's exact 0.0 reproduces its independently-probed
`(0, 1)` layout, which is what validates the method. The determinism measurement stays in the output
because it bears directly on Stage C's A-vs-A verifier.

Run:
    unset PYTHONPATH && uv run python -u logs/p1/step10/probe_nomic_alignment.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

import numpy as np  # noqa: E402

from src.core.config import Settings  # noqa: E402
from src.pdf_ingestion.cluster_embedder import ClusterDenseEmbedder  # noqa: E402

OUT = REPO / "logs" / "p1" / "step10" / "probe_nomic_alignment.json"

TEXT = (
    "Newton's second law states that the net force on an object is equal to the mass of that "
    "object multiplied by its acceleration. This is proportional to the square of the distance "
    "from the source, as we shall now derive. The lever is a rigid bar that rotates about a "
    "fulcrum, and the mechanical advantage equals the ratio of the two arms."
)
SENTINEL = " sentinel"

MODELS = [
    ("nomic-ai/nomic-embed-text-v1.5", "search_document: "),
    ("Qwen/Qwen3-Embedding-0.6B", ""),
]


def probe(model: str, doc_prefix: str, cache_dir: str) -> dict:
    from transformers import AutoTokenizer

    cfg = Settings(
        dense_model=model, dense_dim=768, dense_dim_low=64,
        document_prefix=doc_prefix, sv_embed_url="http://10.0.10.70:8123/embed-text/v1/embeddings",
        use_stub_embedder=False,
    )
    tok = AutoTokenizer.from_pretrained(model, cache_dir=cache_dir)
    emb = ClusterDenseEmbedder(settings=cfg)

    t1, t2 = TEXT, TEXT + SENTINEL
    n1 = len(tok(doc_prefix + t1, add_special_tokens=False)["input_ids"])
    n2 = len(tok(doc_prefix + t2, add_special_tokens=False)["input_ids"])

    def tokens(text: str) -> np.ndarray:
        return np.asarray(emb.embed_documents_tokens([text])[0], dtype=np.float64)

    def pooled(text: str) -> np.ndarray:
        # one row, so the same 2-D determinism check applies to both paths
        return np.asarray(emb.embed_documents([text]), dtype=np.float64).reshape(1, -1)

    # ── determinism: the SAME call twice, on both paths ───────────────────────────────────────
    M1, M1b = tokens(t1), tokens(t1)
    P1, P1b = pooled(t1), pooled(t1)

    def det(a: np.ndarray, b: np.ndarray) -> dict:
        if a.shape != b.shape:
            return {"same_shape": False, "shape_a": list(a.shape), "shape_b": list(b.shape)}
        na = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)
        nb = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-12)
        return {
            "same_shape": True,
            "max_abs_diff": float(np.max(np.abs(a - b))),
            "n_rows_differing": int(np.sum(np.any(a != b, axis=1))),
            "min_row_cosine": float(np.min(np.sum(na * nb, axis=1))),
        }

    det_tok = det(M1, M1b)
    det_pooled = det(P1, P1b)

    # ── alignment, tolerant, with the error PROFILE reported ─────────────────────────────────
    M2 = tokens(t2)
    profile: list[dict] = []
    for o in range(0, max(1, M2.shape[0] - n1 + 1)):
        block = M2[o:o + n1]
        if block.shape != M1[:n1].shape:
            continue
        profile.append({"leading": o,
                        "max_abs_diff": float(np.max(np.abs(M1[:n1] - block)))})
    best = min(profile, key=lambda r: r["max_abs_diff"]) if profile else None
    leading = best["leading"] if best else None
    trailing = None if leading is None else M1.shape[0] - n1 - leading

    # the choice must be UNAMBIGUOUS: the runner-up must be materially worse
    others = sorted((r["max_abs_diff"] for r in profile if leading is None or r["leading"] != leading))
    margin = None
    if best and others:
        margin = round(others[0] / best["max_abs_diff"], 3) if best["max_abs_diff"] > 0 else None

    return {
        "model": model, "document_prefix": doc_prefix,
        "tokenizer_class": type(tok).__name__,
        "n_local_t1": n1, "n_local_t2": n2,
        "n_api_t1": int(M1.shape[0]), "n_api_t2": int(M2.shape[0]),
        "delta_t1": int(M1.shape[0]) - n1, "delta_t2": int(M2.shape[0]) - n2,
        "dim": int(M1.shape[1]), "dim_matches_cfg": bool(M1.shape[1] == cfg.dense_dim),
        "per_token_determinism": det_tok,
        "pooled_determinism": det_pooled,
        "alignment_profile": profile,
        "leading": leading, "trailing": trailing,
        "runner_up_margin_x": margin,
        "verdict": (f"n_api == n_local + {leading} leading + {trailing} trailing"
                    if leading is not None else "NO ALIGNMENT FOUND"),
    }


def main() -> int:
    out = {"probe": "special-token layout + endpoint determinism", "sentinel": SENTINEL,
           "results": []}
    for model, prefix in MODELS:
        try:
            r = probe(model, prefix, "./data/models")
        except Exception as exc:  # noqa: BLE001
            r = {"model": model, "document_prefix": prefix,
                 "error": f"{type(exc).__name__}: {exc}", "verdict": "PROBE FAILED"}
        out["results"].append(r)
        print(f"\n{model}  (doc_prefix={prefix!r})")
        for k, v in r.items():
            if k == "alignment_profile":
                print(f"   {'alignment_profile':26s}: " + "  ".join(
                    f"o={p['leading']}:{p['max_abs_diff']:.3e}" for p in v))
            elif k not in ("model", "document_prefix"):
                print(f"   {k:26s}: {v}")
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
