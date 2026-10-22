#!/usr/bin/env python3
"""
Preflight — verify every dependency a baseline eval needs, BEFORE trusting a score.

A retrieval metric is only meaningful if the lanes that produced it actually ran. This
codebase has several ways for a lane to fail *silently*: a cluster reranker that returns
unranked results, a graph whose chunks are not in the vector store, an intent classifier
that quietly falls back to prototype similarity, ColBERT skipped in embedded-Qdrant mode.
Any of those still yields a plausible-looking number.

So run this first. It prints one screen; anything marked FAIL invalidates the run.

Checks:
    1. Resolved config   — which Qdrant, which Memgraph, which lanes are actually live
    2. Qdrant            — reachable; the 4 collections and their point counts
    3. Memgraph          — reachable; node counts
    4. Graph ↔ Qdrant    — % of graph chunk ids that exist in the vector store, SCOPED:
                           if the collection under test does not hold the graph's own
                           document(s), the check reports SKIP (not measured), not a false
                           "retired content" blocker (§D14 fix (b))
    5. Intent classifier — loads, and its input width matches the embedder
    6. LLM endpoints     — /v1/models, rerank, sparse, multivector

Usage:
    uv run python scripts/preflight.py
    uv run python scripts/preflight.py --qdrant-host 10.0.10.65

Exit code 0 = no blockers, 1 = at least one blocker.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse

import httpx
from rich.console import Console
from rich.table import Table

console = Console()
TIMEOUT = 8.0

RESULTS: list[tuple[str, bool | None, str]] = []


def record(name: str, ok: bool | None, detail: str) -> bool:
    """Record one check. ``ok`` is True (PASS), False (FAIL, a blocker) or **None (SKIP)**.

    SKIP exists for one case: a check that is *not applicable* to the configuration under
    test. Rendering it as PASS would be a lie and rendering it as FAIL would block a run
    for a reason that is not a defect. It is printed in yellow and is never a blocker.
    """
    RESULTS.append((name, ok, detail))
    return bool(ok)


# ── 1. config ────────────────────────────────────────────────────────────────

def check_config(cfg) -> dict:
    from src.core.pipeline_config import load_config

    qdrant_target = cfg.qdrant_url or cfg.qdrant_host or f"path:{cfg.qdrant_local_path}"
    is_local = not (cfg.qdrant_url or cfg.qdrant_host)

    t = Table(title="Resolved configuration", show_header=False)
    t.add_column("key", style="bold")
    t.add_column("value")
    t.add_row("Qdrant", qdrant_target)
    t.add_row("Memgraph", f"{cfg.memgraph_host}:{cfg.memgraph_port}")
    t.add_row("embedding (query+index)", f"{cfg.dense_model} ({cfg.dense_dim}d + {cfg.dense_dim_low}d MRL)")
    t.add_row("embedding (derived indexes)",
              f"{cfg.dense_model} ({cfg.dense_dim}d) — DA/concept collections (§I12; was "
              f"{cfg.embedding_model} {cfg.embedding_dim}d)")
    t.add_row("reranker", f"{cfg.reranker_model}  enabled={cfg.reranker_enabled}")
    t.add_row("colbert", f"enabled={cfg.colbert_enabled}  url={cfg.sv_colbert_url or '(local)'}")
    t.add_row("splade", f"enabled={cfg.splade_enabled}  url={cfg.sv_sparse_url or '(local)'}")
    t.add_row("graph", f"enabled={cfg.intent_router_enabled}  tenant={cfg.global_tenant_id}")
    t.add_row("hyde", str(cfg.hyde_enabled))
    t.add_row("DA lane", str(cfg.da_enabled))
    t.add_row("MMR", f"lambda={cfg.mmr_lambda} candidates={cfg.mmr_candidates}")
    console.print(t)

    # Embedded Qdrant mode silently disables ColBERT (store.py gates on `not is_local`).
    if is_local and cfg.colbert_enabled:
        record("colbert-lane", False,
               "ColBERT is ENABLED but Qdrant is embedded (local path) — store.py skips "
               "the lane in that mode. ColBERT will not run.")
    else:
        record("colbert-lane", True, f"colbert will run ({'server' if not is_local else 'disabled'})")

    pipeline: dict[str, tuple[str, str]] = {}
    try:
        pc = load_config()
        for sec in ("card_generation", "raptor_summarization", "intent_classifier", "evaluation"):
            entry = pc.get(sec, {})
            url = entry.get("base_url") or entry.get("judge_base_url") or ""
            model = entry.get("model") or entry.get("judge_model") or ""
            pipeline[sec] = (str(model), str(url).rstrip("/"))
            record(f"pipeline.{sec}", True, f"{model} @ {url}")
    except Exception as exc:  # noqa: BLE001
        record("pipeline config.yaml", False, f"{type(exc).__name__}: {exc}")

    return {"qdrant_target": qdrant_target, "is_local": is_local, "pipeline": pipeline}


# ── 2. Qdrant ────────────────────────────────────────────────────────────────

def qdrant_client(cfg):
    from qdrant_client import QdrantClient

    if cfg.qdrant_url:
        return QdrantClient(url=cfg.qdrant_url, api_key=cfg.qdrant_api_key or None, timeout=30)
    if cfg.qdrant_host:
        return QdrantClient(host=cfg.qdrant_host, port=cfg.qdrant_port, timeout=30)
    return QdrantClient(path=cfg.qdrant_local_path)


def check_qdrant(cfg) -> object | None:
    try:
        client = qdrant_client(cfg)
        cols = {c.name for c in client.get_collections().collections}
    except Exception as exc:  # noqa: BLE001
        record("qdrant", False, f"unreachable: {type(exc).__name__}: {exc}")
        return None

    record("qdrant", True, f"{len(cols)} collections")
    t = Table(title="Qdrant collections")
    for c in ("points", "vectors", "status"):
        t.add_column(c)
    for name in (cfg.qdrant_collection, cfg.da_collection, cfg.colpali_collection, cfg.concept_collection):
        if name not in cols:
            t.add_row(name, "[red]MISSING[/red]", "[red]MISSING[/red]")
            record(f"qdrant.{name}", False, "collection not found")
            continue
        try:
            info = client.get_collection(name)
            params = info.config.params if info.config else None
            vecs = getattr(params, "vectors", None) if params is not None else None
            vnames = list(vecs.keys()) if vecs is not None and hasattr(vecs, "keys") else ["(unnamed)"]
            n = int(info.points_count or 0)
            t.add_row(name, f"{n:,}", ",".join(vnames))
            record(f"qdrant.{name}", n > 0, f"{n:,} points")
        except Exception as exc:  # noqa: BLE001
            t.add_row(name, "[red]error[/red]", str(exc)[:40])
            record(f"qdrant.{name}", False, str(exc)[:80])
    console.print(t)

    # ── Lane dimension probe (§I12 / §I47) ────────────────────────────────────
    # A collection checked by POINT COUNT alone reads PASS even when it cannot be queried at
    # all. `derivative_artifacts` and `concept_embeddings` held 768d vectors while every query
    # against them carried the dense lane's 1024d, so BOTH lanes returned [] on every query and
    # preflight said nothing about it — the only trace was a WARNING line per query (§I47;
    # §I12's update). This is the check that catches it, and the register asks for it here.
    for name in (cfg.da_collection, cfg.concept_collection):
        if name not in cols:
            continue
        try:
            vecs = client.get_collection(name).config.params.vectors
            size = getattr(vecs, "size", None)
        except Exception as exc:  # noqa: BLE001
            record(f"qdrant.{name}.dim", False, f"unreadable: {type(exc).__name__}: {exc}")
            continue
        if size is None:
            continue        # a named-vector layout; the KB collection is checked elsewhere
        if int(size) == int(cfg.dense_dim):
            record(f"qdrant.{name}.dim", True, f"{size}d == dense_dim — lane is callable")
        else:
            record(
                f"qdrant.{name}.dim", False,
                f"{size}d, but the query side is {cfg.dense_dim}d — every query against this "
                f"lane is REJECTED, so the lane silently returns nothing. It predates the "
                f"dense-lane move (§I12): drop the collection and re-index. See §I47.",
            )
    return client


# ── 3/4. Memgraph + graph↔Qdrant agreement ───────────────────────────────────

def check_memgraph(cfg, client) -> None:
    try:
        from neo4j import GraphDatabase

        driver = GraphDatabase.driver(
            f"bolt://{cfg.memgraph_host}:{cfg.memgraph_port}",
            auth=(cfg.memgraph_user, cfg.memgraph_password),
        )
        with driver.session() as s:
            # Literal Cypher inline, not via a variable/f-string: the neo4j driver types the
            # query parameter as LiteralString precisely to block query injection.
            counts: dict[str, int] = {}
            _r = s.run("MATCH (n:Document) RETURN count(n) AS c").single()
            counts["Document"] = int(_r["c"]) if _r else 0
            _r = s.run("MATCH (n:Page) RETURN count(n) AS c").single()
            counts["Page"] = int(_r["c"]) if _r else 0
            _r = s.run("MATCH (n:Chunk) RETURN count(n) AS c").single()
            counts["Chunk"] = int(_r["c"]) if _r else 0
            _r = s.run("MATCH (n:Concept) RETURN count(n) AS c").single()
            counts["Concept"] = int(_r["c"]) if _r else 0
            graph_ids = {
                str(r["id"]) for r in s.run("MATCH (c:Chunk) RETURN c.id AS id").data()
            }
            # The graph's own Document ids — the scope key for the check below (§D14 fix (b)).
            graph_docs = {
                str(r["id"]) for r in s.run("MATCH (d:Document) RETURN d.id AS id").data()
            }
    except Exception as exc:  # noqa: BLE001
        record("memgraph", False, f"unreachable: {type(exc).__name__}: {exc}")
        record("graph.matches-qdrant", False, "cannot evaluate — Memgraph unreachable")
        return

    record("memgraph", True,
           f"docs={counts['Document']} chunks={counts['Chunk']} concepts={counts['Concept']}")
    console.print(
        f"  Memgraph: Documents={counts['Document']} Pages={counts['Page']} "
        f"Chunks={counts['Chunk']} Concepts={counts['Concept']}"
    )

    if client is None:
        record("graph.matches-qdrant", False, "cannot evaluate — Qdrant unavailable")
        return

    try:
        qd_ids: set[str] = set()
        offset = None
        while True:
            pts, offset = client.scroll(
                cfg.qdrant_collection, limit=1000, offset=offset,
                with_payload=["chunk_id"], with_vectors=False,
            )
            for p in pts:
                cid = (p.payload or {}).get("chunk_id")
                if cid:
                    qd_ids.add(str(cid))
            if offset is None:
                break
    except Exception as exc:  # noqa: BLE001
        record("graph.matches-qdrant", False, f"scroll failed: {exc}")
        return

    dangling = graph_ids - qd_ids

    # ── Scope gate (§D14 fix (b)) ────────────────────────────────────────────────
    # The graph is built from ONE ingest, and chunk ids are `str(uuid.uuid4())` per ingest
    # (chunker.py:147). So a graph built from a different ingest shares no ids with the
    # collection under test and the dangling count above is *meaningless*: it reports 100 %
    # for a graph that is perfectly healthy for its own collection, and then tells the
    # operator to run clean_stale_graph.py — which, against a live collection, would delete
    # a correct graph. Ask the graph itself which documents it holds, and whether this
    # collection holds any of them. If it does not, the graph lane is simply not measured
    # for this collection: report that, name both sides, and do not blame retired content.
    if not graph_docs:
        record("graph.matches-qdrant", None,
               "graph holds no Document nodes — graph lane NOT MEASURED for this collection")
        return

    scoped = None
    scope_err = None
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchAny

        scoped = client.count(
            cfg.qdrant_collection,
            count_filter=Filter(must=[FieldCondition(
                key="document_id", match=MatchAny(any=sorted(graph_docs))
            )]),
            exact=True,
        ).count
    except Exception as exc:  # noqa: BLE001
        scope_err = f"{type(exc).__name__}: {exc}"

    if scoped == 0:
        pct = (100 * len(dangling) / len(graph_ids)) if graph_ids else 0.0
        record("graph.matches-qdrant", None,
               f"MISMATCH: the graph was built from a different ingest — none of its "
               f"{len(graph_docs)} document id(s) is in '{cfg.qdrant_collection}'; the graph "
               f"lane is NOT MEASURED for this collection ({len(dangling):,}/{len(graph_ids):,} "
               f"ids differ, {pct:.1f}%). This is not retired content — do NOT run "
               f"clean_stale_graph.py.")
        console.print(
            f"  [yellow]Graph lane not measured.[/yellow] The graph's document(s) "
            f"{sorted(graph_docs)} are not in '{cfg.qdrant_collection}'. The graph is correct "
            f"for the collection it was built from; the multihop lane will return nothing for "
            f"this run. Rebuild the graph against this collection (Phase 3 / Step 9) to measure it."
        )
        return

    pct = (100 * len(dangling) / len(graph_ids)) if graph_ids else 0.0
    # NOTE: no square brackets in these details. rich parses `[...]` in a table cell as
    # MARKUP and silently DROPS an unrecognised tag — a detail like "[graph doc(s) present]"
    # disappears from the verdict table with no error at all. Parentheses only.
    detail = f"{len(dangling):,}/{len(graph_ids):,} graph chunk ids absent from Qdrant ({pct:.1f}%)"
    if scoped is not None:
        detail += f"  (graph doc(s) present in collection: {scoped:,} point(s))"
    if scope_err is not None:
        # Could not resolve the scope — fall back to the unscoped check and SAY SO, so a
        # silent fallback cannot masquerade as a scoped pass.
        detail += f"  (scope gate unavailable: {scope_err})"
    # <1% is tolerable noise; anything more means a retired ingest is still in the graph.
    record("graph.matches-qdrant", pct < 1.0, detail)
    if pct >= 1.0:
        console.print(
            f"  [red]Graph has retired content.[/red] {detail}\n"
            f"  Fix: uv run python scripts/clean_stale_graph.py --qdrant-host <host> --dry-run"
        )


# ── 5. intent classifier ─────────────────────────────────────────────────────

def check_classifier(cfg) -> None:
    import os

    path = cfg.intent_classifier_path
    if not os.path.exists(path):
        record("intent-classifier", False,
               f"missing at {path} — router falls back to prototype similarity SILENTLY")
        return
    try:
        import joblib
        from sklearn.linear_model import LogisticRegression

        model = joblib.load(path)
        width = getattr(model, "n_features_in_", None)
        ok_type = isinstance(model, LogisticRegression)
        # The router classifies the dense-lane query vector (cfg.dense_dim), so the
        # classifier's feature width must match THAT — not the legacy 768d embedder.
        ok = ok_type and width == cfg.dense_dim
        detail = (
            f"loaded {type(model).__name__}, n_features_in_={width} "
            f"(dense lane={cfg.dense_dim})"
        )
        if not ok_type:
            detail = f"not a LogisticRegression ({type(model).__name__}) — predictions will be garbage"
        elif width != cfg.dense_dim:
            detail += ("  ← MISMATCH: predictions will be invalid; re-train with "
                       "scripts/train_intent_classifier.py --train-only")
        record("intent-classifier", ok, detail)
    except Exception as exc:  # noqa: BLE001
        record("intent-classifier", False, f"failed to load: {type(exc).__name__}: {exc}")


# ── 6. LLM endpoints ─────────────────────────────────────────────────────────

def _probe(label: str, url: str, payload: dict | None = None, method: str = "get") -> None:
    if not url:
        record(label, False, "URL not configured")
        return
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            if method == "get":
                r = c.get(url)
            else:
                r = c.post(url, json=payload)
        record(label, r.status_code < 400, f"HTTP {r.status_code}  {url}")
    except Exception as exc:  # noqa: BLE001
        record(label, False, f"{type(exc).__name__}  {url}")


def check_endpoints(cfg) -> None:
    base = (cfg.openai_api_base or "").rstrip("/")
    if not base:
        record("llm.endpoint", False, "OPENAI_API_BASE is empty")
        return
    _probe("llm.models", f"{base}/v1/models")
    _probe("llm.rerank", cfg.sv_rerank_url or "",
           {"model": cfg.reranker_model, "query": "x", "documents": ["a", "b"], "top_k": 2}, "post")
    _probe("llm.sparse", cfg.sv_sparse_url or "",
           {"model": cfg.splade_model, "input": ["x"]}, "post")
    _probe("llm.multivector", cfg.sv_colbert_url or "",
           {"model": cfg.colbert_model, "input": ["x"], "is_query": True}, "post")


def check_completions(pipeline: dict) -> None:
    """Actually generate, per configured pipeline model.

    A probe against /v1/models proves nothing: the gateway answers it from its
    registry while the backend behind a given model may be dead. Observed on .70 —
    `openai/gpt-oss-120b` lists fine and 502s on every call, so a models-only probe
    reports all-clear on a pipeline that cannot generate a single token. Liveness
    has to be a real completion.
    """
    seen: set[tuple[str, str]] = set()
    for sec, (model, url) in sorted(pipeline.items()):
        if not model or not url or (model, url) in seen:
            continue
        seen.add((model, url))
        label = f"llm.completion[{sec}]"
        try:
            with httpx.Client(timeout=90.0) as c:
                r = c.post(
                    f"{url}/chat/completions",
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": "Reply with the single word OK"}],
                        # gpt-oss spends tokens on reasoning before emitting content;
                        # a small budget yields content=None and looks like a failure.
                        "max_tokens": 64,
                        "temperature": 0,
                    },
                )
            if r.status_code >= 400:
                record(label, False, f"HTTP {r.status_code} {r.text[:110]}")
                continue
            msg = r.json()["choices"][0]["message"]
            # Reasoning-only is still alive; empty outright is not usable.
            got = (msg.get("content") or "").strip() or (msg.get("reasoning") or "").strip()
            record(label, bool(got),
                   f"{model} -> {got[:36]!r}" if got else f"{model} returned empty content")
        except Exception as exc:  # noqa: BLE001
            record(label, False, f"{type(exc).__name__}: {exc}")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="Verify baseline prerequisites")
    p.add_argument("--qdrant-host", default=None, help="Override QDRANT_HOST")
    p.add_argument("--qdrant-port", type=int, default=None, help="Override QDRANT_PORT")
    args = p.parse_args()

    from src.core.config import get_settings

    cfg = get_settings()
    if args.qdrant_host:
        cfg.qdrant_host = args.qdrant_host
        cfg.qdrant_url = ""
        if args.qdrant_port:
            cfg.qdrant_port = args.qdrant_port

    console.print("\n[bold]Synapse — baseline preflight[/bold]\n")
    info = check_config(cfg)
    client = check_qdrant(cfg)
    check_memgraph(cfg, client)
    check_classifier(cfg)
    check_endpoints(cfg)
    check_completions(info.get("pipeline", {}))

    t = Table(title="Verdict")
    t.add_column("check")
    t.add_column("result")
    t.add_column("detail")
    blockers = 0
    for name, ok, detail in RESULTS:
        if ok is False:
            blockers += 1
        if ok is None:
            mark = "[yellow]SKIP[/yellow]"
        else:
            mark = "[green]PASS[/green]" if ok else "[red]FAIL[/red]"
        t.add_row(name, mark, detail)
    console.print(t)

    if blockers:
        console.print(f"\n[bold red]{blockers} BLOCKER(S)[/bold red] — a baseline run would be misleading.\n")
        sys.exit(1)
    skipped = [n for n, ok, _ in RESULTS if ok is None]
    if skipped:
        console.print(
            f"\n[bold yellow]No blockers[/bold yellow], but {len(skipped)} check(s) were SKIPPED "
            f"({', '.join(skipped)}) — read the SKIP rows above before trusting a graph-lane number.\n"
        )
        return
    console.print("\n[bold green]All checks passed — safe to run the baseline.[/bold green]\n")


if __name__ == "__main__":
    main()
