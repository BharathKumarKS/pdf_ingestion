#!/usr/bin/env python3
"""P0 verifier — the §I119 config-default revert, the `.env` mechanism, and the read-path guard.

Independent, stdlib-only, re-derives every claim from SOURCE (config.py text, the `.env` file, the
`store` module), NOT from the tests. Prints PASS/FAIL per check and exits non-zero on any failure.

    unset PYTHONPATH && .venv/bin/python logs/p1/step10/p0_config_guard_verifier.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


def main() -> int:
    cfg_src = (ROOT / "src/core/config.py").read_text()
    env_src = (ROOT / ".env").read_text()

    print("P0 — config-default revert (§I119)")

    # C1 — the CODE defaults are the NEUTRAL (Qwen-1024) values, read from source text.
    check("C1a dense_model default is Qwen",
          'dense_model: str = "Qwen/Qwen3-Embedding-0.6B"' in cfg_src)
    check("C1b dense_dim default is 1024",
          re.search(r"dense_dim: int = 1024\b", cfg_src) is not None)
    check("C1c document_prefix default is empty",
          'document_prefix: str = ""' in cfg_src)
    check("C1d query_instruction default is the Qwen instruction",
          'Instruct: Given a physics question, retrieve textbook passages that answer it\\nQuery: '
          in cfg_src)

    # C2 — the VERIFIED additions survived the revert.
    check("C2a derived_query_instruction pinned to nomic",
          'derived_query_instruction: str = "search_query: "' in cfg_src)
    check("C2b sv_colbert_model/sv_sparse_model are EMPTY",
          'sv_colbert_model: str = ""' in cfg_src and 'sv_sparse_model: str = ""' in cfg_src)
    check("C2c graph_max_hops present, default 1",
          re.search(r"graph_max_hops: int = 1\b", cfg_src) is not None)

    print("P0 — the `.env` mechanism")
    # C3 — `.env` carries the DEPLOYED (nomic-768) values.
    check("C3a .env sets DENSE_MODEL=nomic",
          re.search(r"^DENSE_MODEL=nomic-ai/nomic-embed-text-v1\.5\s*$", env_src, re.M) is not None)
    check("C3b .env sets DENSE_DIM=768",
          re.search(r"^DENSE_DIM=768\s*$", env_src, re.M) is not None)
    check("C3c .env sets QUERY_INSTRUCTION with a trailing space (quoted)",
          'QUERY_INSTRUCTION="search_query: "' in env_src)
    check("C3d .env sets DOCUMENT_PREFIX with a trailing space (quoted)",
          'DOCUMENT_PREFIX="search_document: "' in env_src)

    # C4 — a Settings() built WITH the real `.env` resolves to the deployed world, and a Settings()
    # under the test-pinned env resolves to the neutral world (the hermeticity the conftest buys).
    import os
    from src.core.config import Settings
    for k in ("DENSE_MODEL", "DENSE_DIM", "QUERY_INSTRUCTION", "DOCUMENT_PREFIX"):
        os.environ.pop(k, None)
    live = Settings()
    check("C4a live Settings resolves to the DEPLOYED nomic-768 world",
          live.dense_model == "nomic-ai/nomic-embed-text-v1.5" and live.dense_dim == 768
          and live.query_instruction == "search_query: "
          and live.document_prefix == "search_document: ",
          f"{live.dense_model}/{live.dense_dim}")

    print("P0 — the read-path width guard")
    # C5 — the guard raises on a mismatch and is silent on a match / an unreadable schema.
    from types import SimpleNamespace

    import numpy as np

    from src.pdf_ingestion.store import _assert_query_width

    vectors_768 = {"dense_full": SimpleNamespace(size=768)}
    cfg = Settings(dense_dim=1024, dense_model="Qwen/Qwen3-Embedding-0.6B", qdrant_collection="kb")

    raised = None
    try:
        _assert_query_width(np.ones(1024, dtype=np.float32), vectors_768, "dense_full", cfg)
    except RuntimeError as exc:
        raised = str(exc)
    check("C5a RAISES on a 1024d query into a 768d collection",
          raised is not None and "768d" in raised and "1024d" in raised and "DENSE_MODEL" in raised)

    ok = True
    detail = ""
    try:
        _assert_query_width(np.ones(768, dtype=np.float32), vectors_768, "dense_full", cfg)
        _assert_query_width(np.ones(1024, dtype=np.float32), {"dense_full": object()},
                            "dense_full", cfg)
    except Exception as exc:  # noqa: BLE001
        ok = False
        detail = f"{type(exc).__name__}: {exc}"
    check("C5b silent on a match and on an unreadable (stub) schema", ok, detail)

    print()
    if FAILS:
        print(f"RESULT: FAIL — {len(FAILS)} check(s): {FAILS}")
        return 1
    print("RESULT: PASS — all checks green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
