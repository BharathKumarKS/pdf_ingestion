#!/usr/bin/env python
"""A1 — the QUERY-SIDE `matched_concepts` baseline for §G3. 2026-10-20.

Why this exists
---------------
§I29: the §G plan's G3 verifier-3 names a quantity that is *already* 0.9687 (the share
of chunks mentioning >= 2 concepts — a chunk's TOTAL concept count). It cannot
discriminate: only 115/3,672 = 3.1 % of concept-bearing chunks sit at exactly 1, so
that verifier has 3.1 points of headroom and a regression would look like a success.

The quantity §I2 actually means is QUERY-SIDE. `GraphBuilder.graph_search`
(`src/pdf_ingestion/graph_builder.py:449-459`) ranks a chunk by
`size(collect(DISTINCT k.name))` over the QUERY's `top_k=8` concepts, then
`ORDER BY matched_concepts DESC`. That is what §I2 means by "ties at 1" — and it has
never been measured. Without this number G3 would be designed against an unmeasured
baseline, which is the exact mistake §I29 caught in the plan.

What this measures (read-only, no LLM, deterministic)
-----------------------------------------------------
For every query in the v2 gold set:
  1. embed the RAW query with **nomic-ai/nomic-embed-text-v1.5 (768d)** via the
     cluster embed service — the model `Concept.embedding` actually uses (§I12 keeps
     the graph lane on the 768d legacy model);
  2. take the top-8 concepts EXACTLY as `GraphBuilder._find_concepts_scored(vec, 8)`
     does (Qdrant ANN over `concept_embeddings`);
  3. run the SAME ranking Cypher `graph_search` runs, but with no LIMIT, so the whole
     `matched_concepts` distribution for that query is visible (a LIMIT truncates it
     to the top few, which is the thing we are trying to look past);
  4. also call the REAL `GraphBuilder.graph_search(..., limit=5)` so the production
     path's own output is on record and can be compared against (3).

The raw query is embedded directly, so the HyDE non-reproducibility trap does not
apply here — no LLM is called.

Reproducibility is a REQUIREMENT, not a hope (the plan's verifier 2): every set-valued
output is sorted, scores are rounded, and the JSON is dumped with `sort_keys=True`, so
two runs must be BYTE-IDENTICAL. Nothing wall-clock-dependent goes into the JSON for
exactly that reason — timing is printed to stdout (the .log) instead.

Run:
    unset PYTHONPATH && export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v2
    uv run python logs/p1/step10/g3_query_side_baseline.py \
        [--out logs/p1/step10/g3_query_side_baseline.json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import httpx  # noqa: E402
import numpy as np  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.graph_builder import GraphBuilder  # noqa: E402

QUERIES = "data/eval_queries_v2.json"
TOP_K_CONCEPTS = 8          # graph_builder.graph_search: `_find_concepts_scored(vec, top_k=8)`
RETRIEVAL_LIMIT = 5         # graph_search's default `limit`
SCORE_DP = 6                # round ANN scores before emitting, so floats cannot drift the JSON

# The ranking Cypher, copied verbatim from graph_builder.graph_search (lines 449-459)
# MINUS the LIMIT — we want the whole distribution, not the top 5. The ORDER BY is kept
# so the Python-side tie-break matches the production ordering exactly.
_RANK_CYPHER = """
UNWIND $concepts AS c
MATCH (k:Concept {name: c.name})
MATCH (ch:Chunk)-[:MENTIONS]->(k)
WHERE ch.tenant_id IN [$tenant_id, 'global']
WITH ch, collect(DISTINCT k.name) AS matched, sum(c.score) AS concept_score
RETURN ch.id AS chunk_id, matched AS concept_path,
       size(matched) AS matched_concepts, concept_score
"""


def embed_nomic(client: httpx.Client, url: str, model: str, text: str, attempts: int = 3):
    """One 768d query embedding from the cluster embed service. Deterministic."""
    last = None
    for i in range(attempts):
        try:
            r = client.post(url, json={"model": model, "input": [text]})
            r.raise_for_status()
            items = sorted(r.json()["data"], key=lambda it: it.get("index", 0))
            return [float(x) for x in items[0]["embedding"]]
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"embed failed for {text!r}: {last}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="logs/p1/step10/g3_query_side_baseline.json")
    ap.add_argument("--limit", type=int, default=0, help="0 = all queries (default)")
    ap.add_argument("--anchor", default="gold-062", help="query id for the by-eye sanity anchor")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an existing --out artifact (refused by default)")
    args = ap.parse_args()

    # REFUSE TO CLOBBER A REGISTERED ARTIFACT. On 2026-10-20 an independent reviewer re-ran
    # this script without --out, so it wrote to the default artifact path, and did so under a
    # python whose environment could not reach Qdrant — the concept search returned nothing
    # and the script wrote an ALL-ZEROS JSON over the good artifact, then reviewed that. The
    # artifact must not be silently destroyable by a re-run.
    if Path(args.out).exists() and not args.force:
        print(
            f"REFUSING to overwrite {args.out} — it is a registered artifact.\n"
            f"Re-run with --out <scratch path> to check the script, or --force to replace it.",
            file=sys.stderr,
        )
        return 4

    cfg = get_settings()
    with open(QUERIES, encoding="utf-8") as fh:
        raw = json.load(fh)
    queries = [q for q in raw if q.get("id") and q.get("id") != "_note"]
    queries.sort(key=lambda q: q["id"])          # deterministic order, independent of file order
    if args.limit:
        queries = queries[: args.limit]

    # UP-FRONT REACHABILITY, and a real one: if the concept collection cannot be read, the
    # concept search below returns [] for every query and this script would otherwise emit a
    # clean-looking all-zeros artifact. Fail here instead.
    from src.core.database import get_qdrant
    try:
        info = get_qdrant(cfg).get_collection(cfg.concept_collection)
        n_concepts = int(info.points_count or 0)
        if n_concepts == 0:
            print(f"ABORT: {cfg.concept_collection} has 0 points", file=sys.stderr)
            return 3
    except Exception as exc:  # noqa: BLE001
        print(f"ABORT: cannot read {cfg.concept_collection} on {cfg.qdrant_host}: {exc}",
              file=sys.stderr)
        return 3
    print(f"concept collection {cfg.concept_collection}: {n_concepts:,} points on "
          f"{cfg.qdrant_host}:{cfg.qdrant_port}")

    gb = GraphBuilder(cfg)
    tenant = cfg.global_tenant_id

    out_queries: list[dict] = []
    agg_hist: Counter = Counter()                # matched_concepts over ALL matching chunks
    agg_topk_medians: list[float] = []
    topk_median_hist: Counter = Counter()
    graph_search_parity = 0
    n_embed_err = 0
    n_no_concepts = 0

    t0 = time.time()
    with httpx.Client(timeout=60.0) as client:
        for i, q in enumerate(queries, 1):
            qid, text = q["id"], q["query"]
            try:
                vec = embed_nomic(client, cfg.sv_embed_url, cfg.embedding_model, text)
            except Exception as exc:  # noqa: BLE001
                n_embed_err += 1
                out_queries.append({"id": qid, "error": f"embed: {exc}"})
                continue
            if len(vec) != cfg.embedding_dim:
                raise SystemExit(
                    f"{qid}: embed returned {len(vec)}d, expected {cfg.embedding_dim}d "
                    f"({cfg.embedding_model}) — the graph lane is 768d (§I12)"
                )

            # (2) the top-8 concepts, exactly as graph_search does it
            scored = gb._find_concepts_scored(  # noqa: SLF001 — faithful to the production path
                __import__("numpy").asarray(vec, dtype="float32"), top_k=TOP_K_CONCEPTS
            )
            concept_names = [n for n, _ in scored]
            if not concept_names:
                # The concept search returned nothing for a real query. That is the exact
                # signature of an unreachable/misconfigured concept collection, and it would
                # otherwise show up as an innocuous empty histogram. Count it loudly.
                n_no_concepts += 1

            # (3) the full ranking, no LIMIT
            rows = []
            if concept_names:
                with gb._get_driver().session() as s:  # noqa: SLF001
                    rows = s.run(
                        _RANK_CYPHER,
                        concepts=[{"name": n, "score": round(sc, SCORE_DP)} for n, sc in scored],
                        tenant_id=tenant,
                    ).data()
            # deterministic order: the production ORDER BY, with chunk_id as the final tie-break
            rows.sort(key=lambda r: (-r["matched_concepts"], -round(r["concept_score"], SCORE_DP),
                                     str(r["chunk_id"])))

            hist = Counter(r["matched_concepts"] for r in rows)
            agg_hist.update(hist)
            topk = rows[:RETRIEVAL_LIMIT]
            topk_mc = [r["matched_concepts"] for r in topk]
            topk_med = statistics.median(topk_mc) if topk_mc else None
            if topk_med is not None:
                agg_topk_medians.append(topk_med)
                topk_median_hist[topk_med] += 1

            # (4) the real production call, for parity
            prod = gb.graph_search(
                text, tenant,
                query_vector=np.asarray(vec, dtype=np.float32), limit=RETRIEVAL_LIMIT,
            )
            prod_mc = [r["matched_concepts"] for r in prod]
            if prod_mc == topk_mc:
                graph_search_parity += 1

            out_queries.append({
                "id": qid,
                "query": text,
                "query_type": q.get("query_type"),
                "answerable": q.get("answerable"),
                "expected_route": q.get("expected_route"),
                "query_vec_sha256": hashlib.sha256(
                    json.dumps(vec).encode()
                ).hexdigest(),
                "top8_concepts": [[n, round(sc, SCORE_DP)] for n, sc in scored],
                "chunks_matching_any_concept": len(rows),
                "matched_concepts_histogram": {str(k): hist[k] for k in sorted(hist)},
                "topk_matched_concepts": topk_mc,
                "topk_median": topk_med,
                "topk_chunks": [
                    {"chunk_id": str(r["chunk_id"]),
                     "matched_concepts": r["matched_concepts"],
                     "concept_score": round(r["concept_score"], SCORE_DP)}
                    for r in topk
                ],
                "graph_search_parity": prod_mc == topk_mc,
            })
            if i % 25 == 0:
                print(f"  [{i}/{len(queries)}] {qid} … {time.time() - t0:.0f}s", flush=True)

    gb.close()

    ok = [q for q in out_queries if "error" not in q]
    n_chunks = sum(agg_hist.values())
    if n_chunks == 0:
        # LOUD FAILURE, no artifact. An all-zeros artifact is worse than no artifact: it looks
        # like a result and it is indistinguishable from a genuinely empty measurement.
        print(
            f"\nABORT: 0 chunks matched any concept across {len(ok)} queries "
            f"({n_no_concepts} queries resolved no concepts at all).\n"
            f"The concept search or the graph is not reachable — NOT writing {args.out}.",
            file=sys.stderr,
        )
        return 3
    ge2 = sum(v for k, v in agg_hist.items() if k >= 2)
    ge3 = sum(v for k, v in agg_hist.items() if k >= 3)
    distinct_values = sorted(agg_hist)

    def _slice(key):
        sub = Counter()
        for q in ok:
            for k, v in q["matched_concepts_histogram"].items():
                sub[int(k)] += v
        return sub

    by_type = {}
    for qt in sorted({q["query_type"] for q in ok if q.get("query_type")}):
        sub = Counter()
        for q in ok:
            if q["query_type"] == qt:
                for k, v in q["matched_concepts_histogram"].items():
                    sub[int(k)] += v
        by_type[qt] = {"chunks": sum(sub.values()),
                       "histogram": {str(k): sub[k] for k in sorted(sub)},
                       "share_ge_2": round(sum(v for k, v in sub.items() if k >= 2) /
                                           sum(sub.values()), 4) if sub else None}

    by_answerable = {}
    for a in (True, False):
        sub = Counter()
        for q in ok:
            if q["answerable"] == a:
                for k, v in q["matched_concepts_histogram"].items():
                    sub[int(k)] += v
        tot = sum(sub.values())
        by_answerable[str(a)] = {
            "queries": sum(1 for q in ok if q["answerable"] == a),
            "chunks": tot,
            "histogram": {str(k): sub[k] for k in sorted(sub)},
            "share_ge_2": round(sum(v for k, v in sub.items() if k >= 2) / tot, 4) if tot else None,
        }

    anchor = next((q for q in ok if q["id"] == args.anchor), None)

    out = {
        "meta": {
            "generated_by": "logs/p1/step10/g3_query_side_baseline.py",
            "what": "query-side matched_concepts distribution (§I29's missing number)",
            "qdrant": f"{cfg.qdrant_host}:{cfg.qdrant_port}",
            "concept_collection": cfg.concept_collection,
            "graph": f"{cfg.memgraph_host}:{cfg.memgraph_port}",
            "embed_model": cfg.embedding_model,
            "embed_dim": cfg.embedding_dim,
            "embed_url": cfg.sv_embed_url,
            "top_k_concepts": TOP_K_CONCEPTS,
            "retrieval_limit": RETRIEVAL_LIMIT,
            "score_dp": SCORE_DP,
            "queries_file": QUERIES,
            "n_queries": len(queries),
            "n_queries_ok": len(ok),
            "n_embed_errors": n_embed_err,
            "n_queries_resolved_no_concepts": n_no_concepts,
            "no_llm_calls": True,
        },
        "aggregate": {
            "matching_chunks_total": n_chunks,
            "matched_concepts_histogram": {str(k): agg_hist[k] for k in distinct_values},
            "distinct_matched_concepts_values": distinct_values,
            "mean_matched_concepts": round(sum(k * v for k, v in agg_hist.items()) / n_chunks, 4)
            if n_chunks else None,
            "share_ge_2": round(ge2 / n_chunks, 4) if n_chunks else None,
            "share_ge_3": round(ge3 / n_chunks, 4) if n_chunks else None,
            "share_exactly_1": round(agg_hist.get(1, 0) / n_chunks, 4) if n_chunks else None,
            "degeneracy": {
                "all_1": set(distinct_values) == {1},
                "all_8": set(distinct_values) == {TOP_K_CONCEPTS},
                "n_distinct_values": len(distinct_values),
                "verdict": "NON-DEGENERATE" if len(distinct_values) > 1 else "DEGENERATE",
            },
            "topk_median_of_medians": statistics.median(agg_topk_medians) if agg_topk_medians else None,
            "topk_median_histogram": {str(k): topk_median_hist[k] for k in sorted(topk_median_hist)},
            "topk_mean_matched_concepts": round(
                sum(k * v for k, v in topk_median_hist.items()) / len(agg_topk_medians), 4)
            if agg_topk_medians else None,
            "graph_search_parity_queries": graph_search_parity,
            "by_query_type": by_type,
            "by_answerable": by_answerable,
        },
        "sanity_anchor": {
            "id": args.anchor,
            "query": anchor["query"] if anchor else None,
            "top8_concepts": anchor["top8_concepts"] if anchor else None,
            "note": "hand-checked on-topic by eye — recorded, not asserted (plan verifier 3)",
        },
        "queries": out_queries,
    }

    Path(args.out).write_text(
        json.dumps(out, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print("\n=== A1 query-side matched_concepts baseline ===")
    print(f"queries: {len(queries)} ({len(ok)} ok, {n_embed_err} embed errors)  "
          f"wall {time.time() - t0:.0f}s")
    print(f"chunks matching >=1 of the query's 8 concepts: {n_chunks:,}")
    print("histogram (matched_concepts -> chunks):")
    for k in distinct_values:
        print(f"   {k}: {agg_hist[k]:>7,}")
    print(f"mean {out['aggregate']['mean_matched_concepts']}   "
          f"share>=2 {out['aggregate']['share_ge_2']}   share>=3 {out['aggregate']['share_ge_3']}   "
          f"exactly-1 {out['aggregate']['share_exactly_1']}")
    print(f"degeneracy: {out['aggregate']['degeneracy']}")
    print(f"top-{RETRIEVAL_LIMIT} median of medians: {out['aggregate']['topk_median_of_medians']}   "
          f"hist {out['aggregate']['topk_median_histogram']}")
    print(f"graph_search parity: {graph_search_parity}/{len(ok)} queries")
    print(f"anchor {args.anchor}: {anchor['top8_concepts'] if anchor else None}")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
