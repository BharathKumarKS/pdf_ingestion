#!/usr/bin/env python
"""§G2 verifiers V2 / V4 / V6 — re-derived from the store, not read off the artifact.

The artifact asserts its own cost ledger and its own connectivity. This script checks those claims
the only way that means anything: by re-reading the graph and the chunk texts and reproducing the
work with a **fake LLM that records every prompt**. No LLM is called, so it is free to run.

  V2  every community is internally connected, at every resolution (Leiden's guarantee — the reason
      the owner chose Leiden over Louvain, which returned a disconnected 75-member community in §I33)
  V4  the cost ledger is COMPLETE and matches what a re-run issues: the fake run's call count equals
      the artifact's `total_calls`, and the ledger's parts sum to its whole
  V6  every leaf prompt carried the FULL SQLite chunk text — never the graph's 500-char
      `Chunk.chunk_text` stub. Checked by looking for each community's complete chunk text inside the
      prompt that was sent for it
  V1r the artifact's resolutions / modularity / nesting reproduce the §G2 GATE's numbers, so the
      partition summarised is the partition the gate approved (the §I50 Finding 4 invariant, re-checked
      after the merge and the rebuild)

    unset PYTHONPATH && uv run python logs/p1/step10/g2_verify_summaries.py \
        --artifact logs/p1/step10/g2_summaries_2026-10-22.json \
        --gate logs/p1/step10/g2_leiden_gate_2026-10-22_post_merge.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from sqlmodel import Session, select  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.database import Chunk, get_engine, get_memgraph  # noqa: E402
from src.pdf_ingestion.community_summaries import (  # noqa: E402
    LEAF_PROMPT,
    build_hierarchy,
    read_concept_chunks,
    read_concept_graph,
    read_concept_names,
    summarize_communities,
)

SEED = 20261020          # must match g2_leiden_gate.py and build_community_summaries.py
STUB_LEN = 500           # graph_builder.py truncates Chunk.chunk_text to this


class RecordingLLM:
    """Records every prompt; returns a deterministic non-empty answer. Makes no network call."""

    def __init__(self):
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return f"stub-summary[{len(prompt)}]"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--gate", required=True)
    ap.add_argument("--doc-id", default="7ba61432-c5e0-416d-aecf-25a232523481")
    ap.add_argument("--sample", type=int, default=25, help="leaf communities to check for V6")
    args = ap.parse_args()

    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
        if not ok:
            failures.append(name)

    art = json.loads(Path(args.artifact).read_text())
    gate = json.loads(Path(args.gate).read_text())
    cost = art["cost"]

    print("=== V2 / V4 / V6 / V1-reproduction ===")
    print(f"artifact: {args.artifact}")
    print(f"  document={art['document']}  resolutions={art['resolutions']}")

    # ── re-read the graph and re-derive the hierarchy ────────────────────────────────────────
    cfg = get_settings()
    driver = get_memgraph(cfg)
    if driver is None:
        print("ERROR: no Memgraph driver", file=sys.stderr)
        return 2
    with driver.session() as session:
        g = read_concept_graph(session, args.doc_id)
        concept_chunks = read_concept_chunks(session, args.doc_id)
        names = read_concept_names(session, args.doc_id)

    hierarchy = build_hierarchy(g, seed=SEED)
    print(f"  graph: {g.number_of_nodes()} nodes, {g.number_of_edges()} edges; "
          f"vocabulary {len(names)} (isolated {len(names) - g.number_of_nodes()})")

    # ── V2 ───────────────────────────────────────────────────────────────────────────────────
    for i, lvl in enumerate(hierarchy.levels):
        conn = lvl.connectivity
        check(f"V2 level {i} (res {lvl.resolution}) all communities connected",
              bool(conn["all_connected"]),
              f"{len(lvl.communities)} communities, disconnected={conn.get('disconnected') or []}")

    # ── V1 reproduction: the artifact partitions the graph the GATE approved ──────────────────
    gate_q = {float(r): gate["ladder"][r]["leiden"]["q"] for r in gate["ladder"]}
    for lvl in hierarchy.levels:
        gq = gate_q.get(float(lvl.resolution))
        check(f"V1r res {lvl.resolution}: builder Q reproduces the gate",
              gq is not None and abs(round(lvl.q, 6) - round(gq, 6)) < 1e-9,
              f"builder={lvl.q:.6f} gate={gq}")
    gate_nest = {k: v["fraction_nested"] for k, v in gate["hierarchy_nesting"].items()}
    check("V1r nesting reproduces the gate",
          all(abs(hierarchy.nesting[i] - gate_nest[k]) < 1e-9
              for i, k in enumerate(["1.0->2.0", "0.5->1.0"])),
          f"builder={hierarchy.nesting} gate={gate_nest}")

    # ── re-run the whole build with a recording fake LLM (no network) ─────────────────────────
    with Session(get_engine(cfg)) as s:
        texts_by_id = {
            c.id: c.text for c in s.exec(select(Chunk)).all()  # type: ignore[attr-defined]
        }
    get_texts = lambda ids: [texts_by_id[i] for i in ids if i in texts_by_id]  # noqa: E731

    llm = RecordingLLM()
    out = summarize_communities(hierarchy, concept_chunks, get_texts, llm=llm, dry_run=False)

    # ── V4 ───────────────────────────────────────────────────────────────────────────────────
    check("V4 total_calls is non-zero and every call is classified",
          out["total_calls"] == len(llm.prompts)
          == out["single_calls"] + out["map_calls"] + out["reduce_calls"],
          f"artifact total={cost['total_calls']}, rerun total={out['total_calls']}, "
          f"prompts={len(llm.prompts)}")
    # JSON turns the int level keys into strings — normalise before comparing
    levels_rerun = {str(k): v for k, v in out["calls_by_level"].items()}
    check("V4 the artifact's ledger reproduces on a re-run",
          out["total_calls"] == cost["total_calls"]
          and levels_rerun == cost["calls_by_level"],
          f"artifact={cost['total_calls']} ({cost['calls_by_level']}) vs "
          f"rerun={out['total_calls']} ({out['calls_by_level']})")
    check("V4 no call returned empty (the run's exit criterion)",
          cost.get("empty_returns") == 0 and out["empty_returns"] == 0,
          f"artifact empty_returns={cost.get('empty_returns')}")
    check("V4 no community was summarised map-reduce at this budget",
          cost.get("batched_communities") == 0 and cost.get("truncated_texts") == 0,
          f"batched={cost.get('batched_communities')} truncated={cost.get('truncated_texts')}")

    # ── V6: leaf prompts carried FULL chunk text, not the 500-char graph stub ────────────────
    leaves = hierarchy.levels[0]
    checked = not_verbatim = long_missing = 0
    for members in leaves.communities[: args.sample]:
        ids = sorted({c for concept in members for c in concept_chunks.get(concept, [])})
        texts = [texts_by_id[i] for i in ids if i in texts_by_id]
        if not texts:
            continue
        checked += 1
        prompt = LEAF_PROMPT.format(body="\n\n---\n\n".join(texts))
        # the prompt the builder would send must be EXACTLY one that was sent — same text, same
        # order, same length. A [:500] slice anywhere fails this.
        if prompt not in llm.prompts:
            not_verbatim += 1
        # ...and every chunk longer than the graph's stub must appear in full inside it
        for t in texts:
            if len(t) > STUB_LEN and t not in prompt:
                long_missing += 1
    check(f"V6 all {checked} sampled leaf prompts carried the FULL text verbatim",
          not_verbatim == 0 and long_missing == 0,
          f"prompts not found verbatim={not_verbatim}, long chunks missing in full={long_missing}")
    long_chunks = sum(1 for t in texts_by_id.values() if len(t) > STUB_LEN)
    check("V6 the corpus really does have chunks longer than the 500-char stub",
          long_chunks > 0, f"{long_chunks} chunks > {STUB_LEN} chars")

    # ── the summaries themselves ─────────────────────────────────────────────────────────────
    summaries = art["summaries"]
    nonempty = {k: v for k, v in summaries.items() if (v or "").strip()}
    expected = out["total_calls"]
    check("artifact: one non-empty summary per call",
          len(nonempty) == expected,
          f"{len(nonempty)} non-empty of {len(summaries)} entries; rerun issued {expected} calls")

    print(f"\n{'ALL CHECKS PASSED' if not failures else 'FAILURES: ' + ', '.join(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
