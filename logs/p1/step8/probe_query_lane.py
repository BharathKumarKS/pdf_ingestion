#!/usr/bin/env python3
"""Step 8 pre-flight — the QUERY side is on the dense lane (IMPROVEMENTS.md §E6).

Live probe against the real cluster. Verifies, in one run:

1. ``get_query_vector`` returns a ``dense_dim`` (1024) unit vector.
2. The query instruction is actually applied — the query vector differs from the
   same text embedded as a *passage* (``embed_documents``), which carries no
   instruction. Without this the query path would silently rank in the wrong space.
3. The 64d MRL view is a re-normalised truncation of the 1024d vector, matching
   what ``store._qdrant_search`` computes inline.
4. The intent router now REJECTS the retired 768d classifier (schema check against
   ``dense_dim``) and falls back to prototypes embedded at 1024d — so a query still
   routes instead of raising a shape error.
5. The dense vector NAME the query side targets is resolved from the collection
   (``dense_1024`` on the re-ingest schema), not hard-coded.

Run:  SV_EMBED_URL=http://10.0.10.70:8123/embed-text/v1/embeddings \
      USE_STUB_EMBEDDER=false uv run python logs/p1/step8/probe_query_lane.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np

from src.core.config import Settings, get_settings
from src.core.intent_router import IntentRouter
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder, get_query_vector

QUERY = "What is Newton's second law of motion?"
evidence: dict = {}


def main() -> int:
    cfg = get_settings()
    print(f"dense_model={cfg.dense_model}  sv_embed_url={cfg.sv_embed_url}")
    assert cfg.sv_embed_url, "SV_EMBED_URL is unset — this probe needs the cluster"
    assert not cfg.use_stub_embedder, "USE_STUB_EMBEDDER is on — this probe needs the cluster"

    # ── 1. dim + unit norm ────────────────────────────────────────────────────
    q = np.asarray(get_query_vector(QUERY, cfg), dtype=np.float32)
    evidence["query_vector_dim"] = int(q.shape[0])
    evidence["query_vector_norm"] = round(float(np.linalg.norm(q)), 6)
    evidence["dense_dim"] = cfg.dense_dim
    assert q.shape == (cfg.dense_dim,), f"expected {cfg.dense_dim}d, got {q.shape}"
    # The endpoint returns unnormalised vectors; the client normalises. A raw 70-norm
    # vector would silently break any dot-product consumer.
    assert np.isclose(np.linalg.norm(q), 1.0, atol=1e-4), (
        f"query vector is not unit-norm ({np.linalg.norm(q)})"
    )

    # ── 2. the instruction is applied ─────────────────────────────────────────
    emb = get_cluster_embedder(cfg)
    passage = np.asarray(emb.embed_documents([QUERY])[0], dtype=np.float32)
    cos = float(np.dot(q, passage))
    evidence["cos_query_vs_passage"] = round(cos, 6)
    evidence["instruction"] = cfg.query_instruction
    # Same text, different lanes: a near-1.0 cosine would mean the instruction is NOT
    # reaching the model and the query is being embedded as a passage.
    assert cos < 0.999, f"instruction appears NOT applied (cos={cos:.6f})"

    # ── 3. the 64d MRL view ───────────────────────────────────────────────────
    from src.pdf_ingestion.cluster_embedder import mrl_slice

    low_helper = mrl_slice(q, cfg.dense_dim_low)
    low_inline = q[: cfg.dense_dim_low].copy()
    low_inline /= np.linalg.norm(low_inline) + 1e-9
    delta = float(np.max(np.abs(low_helper - low_inline)))
    evidence["mrl_slice_max_delta"] = delta
    evidence["mrl_slice_dim"] = int(low_helper.shape[0])
    assert delta < 1e-6, f"MRL slice disagrees with the inline store slice ({delta})"

    # ── 4. the router: classifier accepted iff it matches the dense lane ──────
    import joblib

    clf_path = Path(cfg.intent_classifier_path)
    evidence["classifier_path"] = str(clf_path)
    evidence["classifier_exists"] = clf_path.exists()
    width = None
    if clf_path.exists():
        stale = joblib.load(clf_path)
        width = int(getattr(stale, "n_features_in_", -1))
        evidence["classifier_n_features_in"] = width
    router = IntentRouter(settings=cfg)
    evidence["router_mode"] = "classifier" if router._clf is not None else "prototype"
    if width == cfg.dense_dim:
        assert router._clf is not None, (
            f"a {width}d classifier matches the dense lane but was rejected"
        )
    else:
        # The pre-retrain state: a 768d classifier must be rejected loudly rather than
        # accepted and fed 1024d vectors.
        assert router._clf is None, f"a {width}d classifier must not be accepted by the {cfg.dense_dim}d lane"

    # Classify real dense-lane vectors — the end-to-end check, in whichever mode is live.
    probes = {
        "What is Newton's second law of motion?": ("factual", "mixed"),
        "Give me an overview of classical mechanics": ("overview", "mixed"),
        "Show me the diagram of the double-slit experiment": ("visual", "mixed"),
    }
    routing = {}
    for text, expected in probes.items():
        v = np.asarray(get_query_vector(text, cfg), dtype=np.float32)
        got = router.classify(v).value
        routing[text] = {"intent": got, "expected_any_of": list(expected)}
        assert got in expected, f"{text!r} → {got}, expected one of {expected}"
    evidence["routing"] = routing

    # Prototype matrices exist only in prototype mode; record them when they do.
    if router._proto_matrices:
        evidence["prototype_count"] = sum(m.shape[0] for m in router._proto_matrices.values())
        evidence["prototype_dim"] = int(next(iter(router._proto_matrices.values())).shape[1])

    # ── 5. the target vector name is resolved from the collection ─────────────
    from src.core.database import reset_singletons
    from src.pdf_ingestion.store import DocumentStore

    reset_singletons()
    offline = Settings(
        use_stub_embedder=True,
        use_stub_llm=True,
        qdrant_in_memory=True,
        sqlite_url="sqlite:///./data/probe_step8.db",
        splade_enabled=True,
    )
    store = DocumentStore(offline)
    dense_name = store._dense_vector_name()
    evidence["resolved_dense_vector_name"] = dense_name
    evidence["collection_vector_names"] = sorted(
        (store._collection_vectors() or {}).keys()
    )
    assert dense_name == "dense_1024", f"resolved '{dense_name}', expected dense_1024"

    out = Path(__file__).with_name("evidence.json")
    out.write_text(json.dumps(evidence, indent=2))
    print(json.dumps(evidence, indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
