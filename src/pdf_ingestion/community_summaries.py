"""§G2 — Leiden community hierarchy and its narrative summaries.

Community detection over the concept graph, plus one LLM summary per leaf community merged
upward into parent-community summaries, retrieved by map-reduce **for the global-sensemaking
query only** (`IMPROVEMENTS.md` §G2, `2026-10-22-p1-g2-community-summaries-plan.md`).

This module supplies the *construction* half. Leiden itself lives in `graph_analytics` (and is
not reimplemented here); the modularity-vs-rewired-null gate is a probe
(`logs/p1/step10/g2_leiden_gate.py`) that runs BEFORE anything here spends budget.

Three things the plan is explicit about, and which the code below is shaped by:

* **V6 — summarise the FULL text, not the graph's stub.** The graph stores `Chunk.chunk_text`
  truncated to 500 chars (`graph_builder.py`), so a leaf summary built from the graph is a summary
  of stubs. Leaf prompts therefore take their passages from `concept_chunks` + an injected
  `get_chunk_texts`, which the caller points at SQLite/Qdrant.
* **V4 — keep the cost ledger open.** The tree is LLM calls all the way up, so every call is
  counted, per level. `dry_run` computes the hierarchy and the prompt sizes and makes **no** calls,
  so the spend is visible before it happens.
* **The finest resolution is the leaf.** `0.5` gives few broad communities, `2.0` many tight ones,
  so the ladder is walked finest-first and each level's parent is found in the next coarser level.

Nothing here opens a driver or a client: `read_concept_graph`/`read_concept_chunks` take a
`session`, and the summariser takes `get_chunk_texts` and `llm` callables, so the whole thing is
unit-testable offline with fakes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import networkx as nx

from .graph_analytics import leiden_ladder

# ── reads (session is injected, so tests use a fake) ──────────────────────────────────────────

CONCEPT_NAMES_CYPHER = (
    "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) WHERE c.document_id = $doc "
    "RETURN DISTINCT k.name AS name"
)
# ⚠️ This Cypher is copied VERBATIM from the §G2 gate (`logs/p1/step10/g2_leiden_gate.py`,
# `load_relates_to`) and must stay that way. Leiden is deterministic given `seed`, but
# `graph_analytics.nx_to_igraph` indexes vertices by `list(g.nodes())` — INSERTION ORDER — so two
# readers of the SAME graph produce DIFFERENT partitions. Measured 2026-10-22: the gate's row order
# gives Q=0.783332 / 338 communities at resolution 1.0; a sorted order gives Q=0.776639 / 342 and a
# reversed order 0.783601 / 342 — same 7,398 nodes and 22,799 edges every time. Reading it any other
# way means §G2 summarises a partition the gate never approved.
RELATES_CYPHER = (
    "MATCH (a:Concept)-[r:RELATES_TO]->(b:Concept) "
    "RETURN a.name AS a, b.name AS b, r.weight AS w"
)
CONCEPT_CHUNKS_CYPHER = (
    "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) WHERE c.document_id = $doc "
    "RETURN k.name AS name, collect(DISTINCT c.id) AS chunks"
)


def read_concept_graph(session, document_id: str | None = None) -> nx.Graph:
    """The concept graph the §G2 gate partitions: nodes are `RELATES_TO` endpoints, edges weighted.

    **`document_id` is accepted for API symmetry and is NOT used in the read**, deliberately — the
    gate's `load_relates_to` is unscoped, and matching its row order is what makes this partition
    reproducible against the gate (see the note on `RELATES_CYPHER`). When a second document lands,
    the gate and this reader must be scoped *together*, or the partitions diverge again.

    ⚠️ **Isolated concepts are NOT nodes.** Measured 2026-10-22: adding the 29 concepts that carry no
    `RELATES_TO` edge gives 7,427 nodes and Q=0.7786 at resolution 1.0, against the gate's 7,398
    nodes and Q=0.783332. They are not lost — `read_concept_names` returns the full vocabulary so the
    caller can COUNT them.

    The read is directed, so each edge arrives once per direction; networkx dedupes and the weight is
    taken as the maximum, which is the value both directions carry.
    """
    g = nx.Graph()
    for row in session.run(RELATES_CYPHER).data():
        src, tgt = row.get("a"), row.get("b")
        if not src or not tgt or src == tgt:
            continue
        weight = float(row.get("w") or 1.0)
        if g.has_edge(src, tgt):
            g[src][tgt]["weight"] = max(g[src][tgt]["weight"], weight)
        else:
            g.add_edge(src, tgt, weight=weight)
    return g


def read_concept_names(session, document_id: str) -> list[str]:
    """Every Concept name the document's chunks mention — including the isolated ones.

    `read_concept_graph` drops isolated concepts on purpose (to match the gate); this is how the
    caller reports how many were dropped instead of losing them silently.
    """
    return [
        row["name"]
        for row in session.run(CONCEPT_NAMES_CYPHER, doc=document_id).data()
        if row.get("name")
    ]


def read_concept_chunks(session, document_id: str) -> dict[str, list[str]]:
    """Concept name -> the chunk ids that mention it.

    This is the bridge that lets a leaf community's summary read the chunks behind its concepts,
    and through them the FULL text (V6) — the graph's own `chunk_text` is a 500-char stub.
    """
    return {
        row["name"]: list(row.get("chunks") or [])
        for row in session.run(CONCEPT_CHUNKS_CYPHER, doc=document_id).data()
        if row.get("name")
    }


# ── the hierarchy ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Level:
    """One resolution's partition."""

    resolution: float
    communities: list[frozenset]          # index == community id
    node_to_comm: dict[str, int]
    q: float
    connectivity: dict


@dataclass
class Hierarchy:
    """A finest-first ladder of partitions plus the parent link between adjacent levels."""

    levels: list[Level]                                   # levels[0] = finest = leaves
    parent_of: dict[tuple[int, int], tuple[int, int]]     # (level, comm) -> (level+1, comm)
    nesting: dict[int, float]                             # level -> overlap with the level above

    @property
    def leaf_communities(self) -> list[frozenset]:
        return self.levels[0].communities


def build_hierarchy(
    g: nx.Graph,
    resolutions: Iterable[float] = (0.5, 1.0, 2.0),
    seed: int = 0,
) -> Hierarchy:
    """Run Leiden at each resolution and link each fine community to its coarse parent.

    The ladder is walked **finest-first** (highest resolution first), because a leaf community is
    the tightest one and parents are the broader communities it nests inside. A community's parent
    is the next-coarser community holding the most of its members; ``nesting`` records the fraction
    of fine communities that lie **wholly inside one** coarse community — the §G2 gate's own
    definition (`g2_leiden_gate.nesting`), kept identical so the numbers are comparable to the ones
    on record.

    Deterministic given ``seed`` **and the reader's row order** — `leiden_ladder` is seeded and the
    parent is chosen by a ``(count, -id)`` max, but igraph indexes vertices by insertion order, so
    the caller must read the graph the same way the gate does (`read_concept_graph` does).
    """
    ladder = leiden_ladder(g, resolutions=tuple(sorted(resolutions, reverse=True)), seed=seed)
    levels: list[Level] = []
    for resolution in sorted(ladder, reverse=True):
        entry = ladder[resolution]
        communities = [frozenset(c) for c in entry["communities"]]
        node_to_comm = {node: i for i, c in enumerate(communities) for node in c}
        levels.append(Level(
            resolution=resolution,
            communities=communities,
            node_to_comm=node_to_comm,
            q=entry["q"],
            connectivity=entry["connectivity"],
        ))

    parent_of: dict[tuple[int, int], tuple[int, int]] = {}
    nesting: dict[int, float] = {}
    for level in range(len(levels) - 1):
        fine, coarse = levels[level], levels[level + 1]
        wholly_inside = 0
        for cid, members in enumerate(fine.communities):
            counts: dict[int, int] = {}
            for node in members:
                parent = coarse.node_to_comm.get(node)
                if parent is not None:
                    counts[parent] = counts.get(parent, 0) + 1
            if not counts:
                continue
            parent = max(counts, key=lambda k: (counts[k], -k))
            parent_of[(level, cid)] = (level + 1, parent)
            # The gate's definition, kept identical so the numbers are comparable to the ones on
            # record: a fine community is nested iff EVERY member sits in the same coarse community.
            if len(counts) == 1:
                wholly_inside += 1
        nesting[level] = (
            round(wholly_inside / len(fine.communities), 4) if fine.communities else 0.0
        )

    return Hierarchy(levels=levels, parent_of=parent_of, nesting=nesting)


# ── the summaries (llm and chunk-text source are injected) ────────────────────────────────────

SYSTEM_PROMPT = (
    "You summarise a physics textbook. Be factual and terse; never invent anything that is not "
    "in the supplied material."
)
LEAF_PROMPT = (
    "The passages below are the source material for one topic cluster in a physics textbook. "
    "Write a short summary (3-6 sentences) of the physics they cover.\n\n---\n\n{body}"
)
PARENT_PROMPT = (
    "The summaries below cover sub-topics of one broader topic in a physics textbook. Combine "
    "them into a single summary (3-6 sentences) of the broader topic.\n\n---\n\n{body}"
)


def _default_llm(prompt: str) -> str:
    from src.core.llm import call_llm

    return call_llm(prompt, system=SYSTEM_PROMPT)


def summarize_communities(
    hierarchy: Hierarchy,
    concept_chunks: dict[str, list[str]],
    get_chunk_texts: Callable[[list[str]], list[str]],
    llm: Callable[[str], str] | None = None,
    dry_run: bool = False,
    max_chunks_per_community: int | None = None,
) -> dict:
    """Summarise every community bottom-up: leaves from full passages, parents from child summaries.

    Returns a dict with:

    * ``summaries`` — ``(level, community_id) -> text`` (``""`` for a skipped or dry-run entry);
    * ``calls_by_level`` / ``total_calls`` — the V4 cost ledger;
    * ``prompt_chars_by_level`` — computed even on a dry run, so the spend is visible first;
    * ``skipped_empty`` — communities with no source material (never sent to the model).

    ``get_chunk_texts`` receives a list of chunk ids and must return their FULL text (V6); the
    caller wires it to SQLite/Qdrant. A community whose passages are empty is SKIPPED, not
    summarised from nothing.
    """
    llm = llm or _default_llm

    children: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for child, parent in hierarchy.parent_of.items():
        children.setdefault(parent, []).append(child)

    summaries: dict[tuple[int, int], str] = {}
    calls_by_level: dict[int, int] = {}
    prompt_chars_by_level: dict[int, int] = {}
    skipped_empty = 0

    for level, lvl in enumerate(hierarchy.levels):
        for cid, members in enumerate(lvl.communities):
            if level == 0:
                ids = sorted({
                    chunk for concept in members for chunk in concept_chunks.get(concept, [])
                })
                if max_chunks_per_community is not None:
                    ids = ids[:max_chunks_per_community]
                body = "\n\n---\n\n".join(get_chunk_texts(ids)) if ids else ""
                prompt = LEAF_PROMPT.format(body=body)
            else:
                kids = sorted(children.get((level, cid), []))
                body = "\n\n---\n\n".join(summaries[k] for k in kids if summaries.get(k))
                prompt = PARENT_PROMPT.format(body=body)

            if not body.strip():
                summaries[(level, cid)] = ""
                skipped_empty += 1
                continue

            prompt_chars_by_level[level] = prompt_chars_by_level.get(level, 0) + len(prompt)
            if dry_run:
                summaries[(level, cid)] = ""
                continue
            summaries[(level, cid)] = llm(prompt)
            calls_by_level[level] = calls_by_level.get(level, 0) + 1

    return {
        "summaries": summaries,
        "calls_by_level": calls_by_level,
        "total_calls": sum(calls_by_level.values()),
        "prompt_chars_by_level": prompt_chars_by_level,
        "skipped_empty": skipped_empty,
    }
