"""§I118-adjacent — the DERIVED embedder must not inherit the ARM's query instruction.

`get_derived_embedder` builds a nomic-768 embedder for the derived collections. It copied only
`dense_model`/`dense_dim` and INHERITED `query_instruction` — so under the default config the derived
(nomic) embedder carried **Qwen's** `Instruct: … Query: ` instruction. `step10_env.sh` masks it by
overriding `QUERY_INSTRUCTION="search_query: "`, so it bites only without the env override.

These tests pin: the derived embedder uses `derived_query_instruction`; the ARM still uses the arm's;
the default is nomic's `search_query: `; and the value is overridable.

The discriminating test is `test_derived_embedder_uses_the_derived_instruction`: revert the
`query_instruction` copy in `get_derived_embedder` and it fails.
"""
from __future__ import annotations


def _real(settings, **over):
    """Settings that build a REAL ClusterDenseEmbedder (no stub), with overrides."""
    base = {"use_stub_embedder": False,
            "query_instruction": "Instruct: QWEN-STYLE\nQuery: ",
            "derived_query_instruction": "search_query: "}
    base.update(over)
    return settings.model_copy(update=base)


def test_derived_instruction_default_is_search_query(settings):
    from src.core.config import Settings
    assert Settings().derived_query_instruction == "search_query: "


def test_derived_embedder_uses_the_derived_instruction(settings):
    """THE discriminating test — the derived (nomic) embedder must NOT carry the arm's instruction."""
    from src.pdf_ingestion.cluster_embedder import get_derived_embedder, reset_derived_embedder
    reset_derived_embedder()
    d = get_derived_embedder(_real(settings))
    assert d._model == "nomic-ai/nomic-embed-text-v1.5"
    assert d._instruction == "search_query: ", (
        f"the derived nomic embedder inherited the arm's instruction: {d._instruction!r}")
    assert "QWEN-STYLE" not in d._instruction


def test_arm_embedder_keeps_the_arms_instruction(settings):
    """The fix must not change the ARM's own embedder."""
    from src.pdf_ingestion.cluster_embedder import get_cluster_embedder, reset_cluster_embedder
    reset_cluster_embedder()
    a = get_cluster_embedder(_real(settings))
    assert a._instruction == "Instruct: QWEN-STYLE\nQuery: "


def test_derived_instruction_is_overridable(settings):
    from src.pdf_ingestion.cluster_embedder import get_derived_embedder, reset_derived_embedder
    reset_derived_embedder()
    d = get_derived_embedder(_real(settings, derived_query_instruction="CUSTOM: "))
    assert d._instruction == "CUSTOM: "


def test_derived_embedder_dim_is_the_derived_dim(settings):
    from src.pdf_ingestion.cluster_embedder import get_derived_embedder, reset_derived_embedder
    reset_derived_embedder()
    d = get_derived_embedder(_real(settings, derived_dense_dim=768))
    assert int(getattr(d, "_dim", 0)) == 768
