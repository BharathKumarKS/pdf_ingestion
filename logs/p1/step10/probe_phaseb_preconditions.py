#!/usr/bin/env python3
"""Phase B / B0b — re-verify the plan's preconditions LIVE, before spending hours.

The plan's §4 table was verified 2026-10-19; this re-measures the ones that can
drift (endpoint liveness, the doc's clean-start state, the collection's point
count).  Prints PASS/FAIL per row.  Exit 0 = all live rows PASS.

    uv run python logs/p1/step10/probe_phaseb_preconditions.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

DB = ROOT / "data/synapse.db"
DOC_NEW = "7ba61432-c5e0-416d-aecf-25a232523481"

failures: list[str] = []


def row(name: str, ok: bool, detail: str) -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name:26} {detail}")
    if not ok:
        failures.append(name)


def main() -> int:
    from src.core.config import get_settings
    cfg = get_settings()

    print("=" * 92)
    print("Phase B / B0b — LIVE preconditions")
    print("=" * 92)
    print(f"  collection {cfg.qdrant_collection} @ "
          f"{cfg.qdrant_host or cfg.qdrant_url or cfg.qdrant_local_path}")

    # ── P2: Qdrant reachable + point count ────────────────────────────────
    try:
        from qdrant_client import QdrantClient
        kwargs: dict = {"timeout": 30}
        if cfg.qdrant_url:
            kwargs.update(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key or None)
        elif cfg.qdrant_host:
            kwargs.update(host=cfg.qdrant_host, port=cfg.qdrant_port)
        else:
            kwargs.update(path=cfg.qdrant_local_path)
        qc = QdrantClient(**kwargs)
        n = int(qc.get_collection(cfg.qdrant_collection).points_count or 0)
        row("P2 qdrant", n == 3796, f"{cfg.qdrant_collection} = {n} points (expect 3796)")
        qc.close()
    except Exception as exc:
        row("P2 qdrant", False, f"{type(exc).__name__}: {exc}")

    # ── P3: cluster LLM ───────────────────────────────────────────────────
    # The gateway serves ONLY /v1/... — posting to {base}/chat/completions 404s
    # (the trap Session 3 hit; `_call_openai` builds the same URL).
    try:
        import httpx
        base = (cfg.openai_api_base or "").rstrip("/")
        if base.endswith("/v1"):
            base = base[: -len("/v1")]
        url = f"{base}/v1/chat/completions"
        r = httpx.post(url,
                       json={"model": cfg.openai_model,
                             "messages": [{"role": "user", "content": "say ok"}],
                             "max_tokens": 2048},
                       timeout=90)
        body = ""
        if r.status_code == 200:
            body = (r.json().get("choices") or [{}])[0].get("message", {}).get("content", "") or ""
        row("P3 llm", r.status_code == 200 and bool(body.strip()),
            f"{url} model={cfg.openai_model} -> HTTP {r.status_code} content={body.strip()[:40]!r}")
    except Exception as exc:
        row("P3 llm", False, f"{type(exc).__name__}: {exc}")

    # ── P4: embed endpoint (RAPTOR embeds summaries) ──────────────────────
    try:
        import httpx
        url = (cfg.sv_embed_url or "").rstrip("/")
        r = httpx.post(url, json={"input": ["probe"], "model": cfg.dense_model}, timeout=60)
        row("P4 embed", r.status_code == 200, f"{url} -> HTTP {r.status_code}")
    except Exception as exc:
        row("P4 embed", False, f"{type(exc).__name__}: {exc}")

    # ── P6: doc's clean-start state ───────────────────────────────────────
    con = sqlite3.connect(DB)
    chunks = con.execute("SELECT count(*) FROM chunks WHERE document_id = ?",
                         (DOC_NEW,)).fetchone()[0]
    cards = con.execute("SELECT count(*) FROM cards WHERE document_id = ? AND is_active = 1",
                        (DOC_NEW,)).fetchone()[0]
    nodes = con.execute("SELECT count(*) FROM raptor_nodes WHERE document_id = ? AND is_active = 1",
                        (DOC_NEW,)).fetchone()[0]
    texts = [r[0] for r in con.execute("SELECT text FROM chunks WHERE document_id = ?",
                                       (DOC_NEW,))]
    con.close()

    row("P6 chunks", chunks == 3796, f"doc {DOC_NEW[:8]} has {chunks} chunks (expect 3796)")
    row("P6 cards", cards == 0, f"active cards = {cards} (expect 0 — clean start)")
    row("P6 raptor", nodes == 0, f"active raptor nodes = {nodes} (expect 0 — clean start)")

    # content-filtered denominator (the card denominator)
    try:
        from src.pdf_ingestion import content_filter
        n_content = sum(1 for t in texts if content_filter.is_content(t))
        row("P6 content chunks", n_content == 3791,
            f"content chunks = {n_content} (expect 3791)  [{Path(content_filter.__file__).name}]")
    except Exception as exc:
        row("P6 content chunks", False, f"{type(exc).__name__}: {exc}")

    print()
    print("=" * 92)
    if failures:
        print(f"PRECONDITIONS: FAIL ({len(failures)}) — {failures}")
        print("=" * 92)
        return 1
    print("PRECONDITIONS: ALL PASS")
    print("=" * 92)
    return 0


if __name__ == "__main__":
    sys.exit(main())
