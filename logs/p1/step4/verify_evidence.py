"""Step 4 — author's evidence pack for the independent verifier (single-turn, no tools).

Recomputes the late-chunking result **independently of the module under test**: it calls the
cluster itself, tokenizes with its own AutoTokenizer call, mean-pools with its own numpy code,
and only then compares against what ``LateChunkEmbedder`` produced. The oracle for the module's
output is therefore the raw endpoint response, not the module.

Run:  uv run python logs/p1/step4/verify_evidence.py
Writes logs/p1/step4/evidence.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
URL = "http://10.0.10.70:8123/embed-text/v1/embeddings"
MODEL = "Qwen/Qwen3-Embedding-0.6B"
TEST_BOOK = ROOT / "data" / "base_textbooks" / "test_book.pdf"


def unit(v):
    return v / (np.linalg.norm(v) + 1e-9)


def _synthetic_child(parent, start):
    """A TextChunk covering ``parent.text[start:]`` — the same shape the live test builds."""
    from src.pdf_ingestion.chunker import TextChunk

    return TextChunk(
        chunk_id="synthetic-this", document_id="doc", tenant_id="global", chunk_index=0,
        text=parent.text[start:], char_start=start, char_end=len(parent.text),
        token_count=len(parent.text[start:].split()), page_number=1,
        parent_id=parent.parent_id, parent_text=parent.text,
    )


def main() -> int:
    from transformers import AutoTokenizer

    from src.core.config import Settings
    from src.pdf_ingestion.chunker import SemanticChunker
    from src.pdf_ingestion.cluster_embedder import ClusterDenseEmbedder
    from src.pdf_ingestion.late_chunk_embedder import LateChunkEmbedder
    from src.pdf_ingestion.models import ParentChunk
    from src.pdf_ingestion.parent_chunker import ParentChunker

    cfg = Settings(sv_embed_url=URL, use_stub_embedder=False)
    tok = AutoTokenizer.from_pretrained(MODEL, cache_dir=cfg.model_cache_dir)

    t0 = time.perf_counter()
    doc, parents = ParentChunker(cfg).convert(str(TEST_BOOK))
    children = SemanticChunker(cfg).chunk_parents("doc", "global", parents)
    parse_s = time.perf_counter() - t0

    embedder = ClusterDenseEmbedder(settings=cfg)
    lce = LateChunkEmbedder(settings=cfg, embedder=embedder, tokenizer=tok)

    by_parent: dict[int, list] = {}
    for c in children:
        by_parent.setdefault(c.parent_id, []).append(c)

    evidence: dict = {
        "fixture": TEST_BOOK.name,
        "pages": len(doc.pages),
        "parents": len(parents),
        "children": len(children),
        "parse_seconds": round(parse_s, 1),
    }

    # ── E1: the alignment facts, straight from the recorded probe ──────────────
    evidence["E1_alignment"] = json.loads((HERE / "alignment.json").read_text())["checks"]

    # ── E2: independent recomputation over the whole fixture ───────────────────
    with httpx.Client() as client:
        max_pool_diff = 0.0
        max_mrl_diff = 0.0
        max_low_diff = 0.0
        checked = 0
        fallbacks = 0
        no_token_children = []
        counterfactual_max = 0.0
        token_counts = []
        mismatches = []
        late_by_id: dict[str, np.ndarray] = {}

        for parent in parents:
            kids = by_parent.get(parent.parent_id, [])
            if not parent.text.strip() or not kids:
                continue
            r = client.post(
                URL,
                json={"model": MODEL, "input": [parent.text], "return_token_embeddings": True},
                timeout=600,
            )
            r.raise_for_status()
            raw = np.asarray(r.json()["data"][0]["embedding"], dtype=np.float32)
            raw = raw[0] if raw.ndim == 3 else raw
            offsets = [
                tuple(o)
                for o in tok(parent.text, add_special_tokens=False,
                             return_offsets_mapping=True)["offset_mapping"]
            ]
            token_counts.append(len(offsets))
            content = raw[:-1]

            produced = {e.chunk.chunk_id: e for e in lce.embed_parent(parent, kids)}
            for kid in kids:
                e = produced[kid.chunk_id]
                late_by_id[kid.chunk_id] = e.dense_1024
                idx = [i for i, (ts, te) in enumerate(offsets)
                       if te > kid.char_start and ts < kid.char_end]
                if not idx:
                    fallbacks += 1
                    no_token_children.append(
                        {"parent": parent.parent_id, "span": [kid.char_start, kid.char_end],
                         "chars": len(kid.text)}
                    )
                    expected = content.mean(axis=0)
                else:
                    expected = content[idx].mean(axis=0)
                    # MRL linearity, recomputed by hand on the RAW endpoint matrix
                    mrl_left = unit(unit(expected)[:64])
                    mrl_right = unit(content[idx][:, :64].mean(axis=0))
                    max_mrl_diff = max(max_mrl_diff, float(np.abs(mrl_left - mrl_right).max()))
                exp_norm = unit(expected)
                d = float(np.abs(e.dense_1024 - exp_norm).max())
                max_pool_diff = max(max_pool_diff, d)
                low_expected = unit(exp_norm[:64])
                max_low_diff = max(max_low_diff, float(np.abs(e.dense_64 - low_expected).max()))
                # Counterfactual for the EOS strip: the failure mode it guards against is an
                # off-by-one index shift (a BOS at the front, or a truncated response), not the
                # trailing vector itself — pooling raw[idx] would equal content[idx] because the
                # extra vector sits at the END and never enters an index list built from offsets.
                if idx:
                    shifted = unit(raw[np.asarray(idx) + 1].mean(axis=0))
                    counterfactual_max = max(counterfactual_max,
                                             float(np.abs(shifted - exp_norm).max()))
                if d > 1e-4:
                    mismatches.append({"chunk": kid.chunk_id, "max_diff": d})
                checked += 1

    evidence["E2_independent_recomputation"] = {
        "children_checked": checked,
        "max_abs_diff_dense_1024": max_pool_diff,
        "max_abs_diff_dense_64": max_low_diff,
        "mismatches_gt_1e-4": mismatches[:10],
        "n_mismatches": len(mismatches),
        "fallback_children": fallbacks,
        "fallback_examples": no_token_children[:5],
        "max_abs_diff_if_indices_shifted_by_one": counterfactual_max,
        "eos_strip_note": (
            "The trailing special vector sits at the END, so a naive implementation that never "
            "strips it still pools raw[idx] == content[idx] for every offset-derived index — "
            "the strip is behaviour-neutral HERE and its value is the count assertion, which "
            "turns a future layout change (BOS at the front, a truncated response) into a loud "
            "error instead of a one-token shift of every child vector."
        ),
        "parent_token_counts": {"min": min(token_counts), "max": max(token_counts),
                                "total": sum(token_counts)},
        "mrl_linearity_max_abs_diff": max_mrl_diff,
    }

    # ── E3: the E3 fix, measured on the real model (late vs isolation twin) ────
    # Every child gets its isolation twin (pooled, per-child) so the effect size is a
    # distribution over the fixture, not one cherry-picked example.
    iso_vecs = embedder.embed_documents([c.text for c in children])
    cosines = [
        float(np.dot(late_by_id[c.chunk_id], unit(np.asarray(v, dtype=np.float32))))
        for c, v in zip(children, iso_vecs)
        if c.chunk_id in late_by_id
    ]
    cosines_sorted = sorted(cosines)
    parent0_kids = by_parent.get(parents[0].parent_id, [])
    evidence["E3_late_vs_isolation"] = {
        "children_compared": len(cosines),
        "cosine_min": cosines_sorted[0],
        "cosine_median": cosines_sorted[len(cosines_sorted) // 2],
        "cosine_max": cosines_sorted[-1],
        "n_cosine_below_0_999": sum(1 for c in cosines if c < 0.999),
        "n_cosine_above_0_9999": sum(1 for c in cosines if c > 0.9999),
        "parent0_child_head": parent0_kids[0].text[:80] if parent0_kids else None,
    }
    # The plan's acceptance case: a child that opens mid-parent ("This ...") — its antecedent
    # is in the parent but not in the child. The fixture has no such child, so the case is
    # built synthetically (the same text the live test uses), and alongside it the fixture's
    # *largest* late-vs-isolation divergence is reported so the effect size is not cherry-picked.
    argmin = min(zip(children, cosines), key=lambda t: t[1]) if cosines else None
    synthetic_parent = ParentChunk(
        parent_id=0,
        text=(
            "The lever is a rigid bar that rotates about a fulcrum. "
            "This is the simplest machine of all, and it trades force for distance."
        ),
        page_map={0: 1},
    )
    start = synthetic_parent.text.index("This")
    synthetic_child = _synthetic_child(synthetic_parent, start)
    late_syn = lce.embed_parent(synthetic_parent, [synthetic_child])[0]
    iso_syn = lce.embed_isolated(synthetic_child)
    evidence["E3_this_child"] = {
        "synthetic_head": synthetic_child.text,
        "token_span": list(late_syn.token_span),
        "cosine_late_vs_isolated": float(np.dot(late_syn.dense_1024, iso_syn.dense_1024)),
        "fixture_largest_divergence": (
            {"chunk_id": argmin[0].chunk_id, "head": argmin[0].text[:90],
             "chars": len(argmin[0].text), "cosine": argmin[1]}
            if argmin else None
        ),
    }

    # ── E4: the recorded cost probe ────────────────────────────────────────────
    evidence["E4_cost"] = json.loads((HERE / "cost.json").read_text())

    (HERE / "evidence.json").write_text(json.dumps(evidence, indent=2))
    print(json.dumps({k: v for k, v in evidence.items() if k != "E4_cost"}, indent=2)[:4000])
    print(f"\nwrote {HERE / 'evidence.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
