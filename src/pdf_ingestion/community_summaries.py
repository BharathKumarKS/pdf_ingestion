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

import time
from dataclasses import dataclass
from typing import Callable, Iterable

import networkx as nx

from .graph_analytics import leiden_ladder
from .summary_checkpoint import SummaryCheckpoint, input_digest

# The syllabus' resolution ladder (`Week_Plan/week-5-summer-lesson-plan.pdf`; `graph_analytics`
# walks it finest-first). Named here so `build_hierarchy`'s default and the checkpoint's run key
# cannot drift apart — a checkpoint written under one ladder must not be resumed under another.
DEFAULT_RESOLUTIONS = (0.5, 1.0, 2.0)

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
    resolutions: Iterable[float] = DEFAULT_RESOLUTIONS,
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
SEP = "\n\n---\n\n"

# ── the prompt budget, and why it exists ──────────────────────────────────────────────────────
# MEASURED 2026-10-22 (`logs/p1/step10/g2_prompt_size_probe.py`, `g2_summariser_model_probe.py`,
# `g2_token_ratio_probe.py`):
#
#   * `_default_llm` below calls `src.core.llm.call_llm`, which posts **`cfg.openai_model`** — and
#     `.env` sets that to **`openai/gpt-oss-20b`**. The graph build's concept extraction uses a
#     DIFFERENT model (`Qwen/Qwen3-VL-8B-Instruct`, `config.yaml:concept_extraction`), and the two
#     have very different contexts: gpt-oss-20b is **131,072 tokens**, Qwen3-VL-8B is **15,000**
#     (both read from `/v1/models`). Measure the model the phase actually runs, not the one another
#     phase runs — the first version of this budget was derived from Qwen's 15,000 and was wrong.
#   * REAL physics chunk text tokenises at **4.49-4.53 chars/token** on gpt-oss-20b. (A probe using
#     repeated English filler reports 6.23 — 40 % optimistic — so never size a budget from filler.)
#   * the §G2 leaf prompts are badly skewed: 178 of 218 leaf communities are <= 2,000 chars, while
#     the largest is **273,470 chars (~60k tokens)**.
#
# 400,000 chars is ~88,000 tokens at the measured ratio, leaving ~43,000 for the reasoning trace and
# the answer inside 131,072. At that budget NO community of this corpus batches — one call per leaf
# community, as the plan specifies. The map-reduce path below is the safety net for a community that
# ever does exceed it: before it existed, an oversized prompt was simply refused by the server,
# `call_llm` returned "" (§I24's failure contract) and the community silently ended up with no
# summary at all.
DEFAULT_MAX_PROMPT_CHARS = 400_000


def _overhead(template: str) -> int:
    """The characters a rendered prompt adds around its body."""
    return len(template.format(body=""))


def _batch_texts(texts: list[str], budget_chars: int, overhead: int) -> tuple[list[list[str]], int]:
    """Greedy, order-preserving batches whose RENDERED prompt fits `budget_chars`. Never splits a text.

    Returns ``(batches, n_texts_truncated)``. A single passage that cannot fit a batch on its own is
    truncated to the budget and **counted** — silently dropping the tail of a passage is the V6
    failure in miniature (a summary of part of a stub), so it is reported rather than absorbed.
    """
    room = max(1, budget_chars - overhead)
    batches: list[list[str]] = []
    cur: list[str] = []
    cur_len = 0
    truncated = 0
    for text in texts:
        if len(text) > room:
            text = text[:room]
            truncated += 1
        if cur and cur_len + len(text) + len(SEP) > room:
            batches.append(cur)
            cur, cur_len = [], 0
        cur.append(text)
        cur_len += len(text) + len(SEP)
    if cur:
        batches.append(cur)
    return batches, truncated


def _call(
    llm: Callable[[str], str],
    prompt: str,
    counters: dict,
    on_call: Callable[..., None] | None = None,
    where: tuple[int, int] | None = None,
    kind: str = "single",
) -> str:
    """One LLM call, counted and reported. An empty return is a FAILURE, never a summary (§I25).

    ``on_call`` receives ``(kind, where, prompt_chars, elapsed_seconds, empty)`` for **every** call —
    §I53's monitoring gap: the 597-call build logged nothing per call, so a stalled run and a healthy
    slow one looked identical in the log (§I23's lesson: read the RATE, not a status code).
    """
    counters["calls"] += 1
    counters["prompt_chars"] += len(prompt)
    started = time.monotonic()
    text = llm(prompt) or ""
    if on_call is not None:
        on_call(kind, where, len(prompt), time.monotonic() - started, not text.strip())
    if not text.strip():
        counters["empty_returns"] += 1
    return text


def _summarise_with_batching(
    llm: Callable[[str], str],
    texts: list[str],
    map_template: str,
    budget_chars: int,
    counters: dict,
    on_call: Callable[..., None] | None = None,
    where: tuple[int, int] | None = None,
) -> str:
    """One call if the material fits; otherwise map-reduce. Every call lands in `counters` (V4)."""
    texts = [t for t in texts if t and t.strip()]
    if not texts:
        return ""

    batches, truncated = _batch_texts(texts, budget_chars, _overhead(map_template))
    counters["truncated_texts"] += truncated

    if len(batches) == 1:
        counters["single_calls"] += 1
        return _call(llm, map_template.format(body=SEP.join(batches[0])), counters,
                     on_call, where, "single")

    # MAP — one summary per batch of source material.
    counters["batched_communities"] += 1
    parts: list[str] = []
    for batch in batches:
        counters["map_calls"] += 1
        text = _call(llm, map_template.format(body=SEP.join(batch)), counters,
                     on_call, where, "map")
        if text.strip():
            parts.append(text)

    # REDUCE — merge the batch summaries, re-batching if they are themselves too many to fit.
    while len(parts) > 1:
        groups, _ = _batch_texts(parts, budget_chars, _overhead(PARENT_PROMPT))
        merged = []
        for group in groups:
            counters["reduce_calls"] += 1
            text = _call(llm, PARENT_PROMPT.format(body=SEP.join(group)), counters,
                         on_call, where, "reduce")
            if text.strip():
                merged.append(text)
        if len(merged) >= len(parts):     # cannot shrink further — stop rather than loop
            break
        parts = merged
    return parts[0] if parts else ""


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
    max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS,
    checkpoint: SummaryCheckpoint | None = None,
    on_call: Callable[..., None] | None = None,
) -> dict:
    """Summarise every community bottom-up: leaves from full passages, parents from child summaries.

    Returns a dict with:

    * ``summaries`` — ``(level, community_id) -> text`` (``""`` for a skipped or dry-run entry);
    * ``calls_by_level`` / ``total_calls`` — the V4 cost ledger;
    * ``prompt_chars_by_level`` — computed even on a dry run, so the spend is visible first.
      ⚠️ On a **dry run this covers the leaf level only**: a parent's prompt is built from its
      children's *summaries*, which do not exist until the run happens, so the parent levels' cost
      is not estimable before the spend. The number of parent calls is (it is
      ``len(communities)`` per level, less any with no children).
    * ``skipped_empty`` — communities with no source material (never sent to the model). On a real
      run this is a leaf with no chunks or a parent whose children all produced nothing.
    * ``deferred_parents`` — **dry run only**: parents that HAVE children and so have source
      material, but whose body is empty because the dry run never generated the child summaries it
      merges. They are counted here rather than as ``skipped_empty`` so the pre-flight report does
      not claim 403 communities of the live graph are source-less when they are not.
    * ``empty_returns`` — calls the model answered with nothing. `call_llm` returns ``""`` on
      failure rather than raising (§I24), so this is the run's real failure count and **the exit
      criterion for a real run** — never the absence of an exception (§I25).
    * ``map_calls`` / ``reduce_calls`` / ``batched_communities`` / ``truncated_texts`` — the batching
      ledger. A community whose material does not fit ``max_prompt_chars`` is summarised map-reduce.
      ⚠️ The budget is derived from the **summariser's** context — `cfg.openai_model`, which is a
      DIFFERENT model from the graph build's extractor; see the comment on
      ``DEFAULT_MAX_PROMPT_CHARS`` before changing it.
    * ``planned_leaf_prompts`` / ``planned_leaf_batched_communities`` — what a real run WOULD do at
      the leaf level, computed on a dry run from the input text alone (so the pre-flight cost report
      stays honest now that one community is no longer one call). ``planned_leaf_prompts`` is the
      number of leaf PROMPTS — single-batch communities included, reduce calls excluded — and the
      exact quantity to compare it to on a real run is ``leaf_prompt_calls``. ⚠️ Not ``map_calls``
      (excludes single-batch communities) and not ``calls_by_level[0]`` (includes the leaf reduce
      calls); both comparisons were made here and both were wrong.

    ``get_chunk_texts`` receives a list of chunk ids and must return their FULL text (V6); the
    caller wires it to SQLite/Qdrant. A community whose passages are empty is SKIPPED, not
    summarised from nothing.

    ``checkpoint`` (§I53) makes the walk resumable: a community whose recorded input digest matches
    the material being summarised now is reused with **no call**, and one whose calls returned empty
    is re-attempted. It is a side-car — the artifact stays the single write point. ``on_call`` is
    invoked once per LLM call with ``(kind, where, prompt_chars, elapsed, empty)`` so a run can be
    watched call by call; §I53 measured a 597-call build that logged nothing per call.
    """
    llm = llm or _default_llm

    children: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for child, parent in hierarchy.parent_of.items():
        children.setdefault(parent, []).append(child)

    summaries: dict[tuple[int, int], str] = {}
    calls_by_level: dict[int, int] = {}
    prompt_chars_by_level: dict[int, int] = {}
    skipped_empty = 0
    deferred_parents = 0
    counters = {
        "calls": 0, "empty_returns": 0, "single_calls": 0, "map_calls": 0, "reduce_calls": 0,
        "batched_communities": 0, "truncated_texts": 0, "prompt_chars": 0,
    }
    planned_leaf_prompts = 0          # dry run: leaf prompts a real run would issue (single + map)
    planned_leaf_batched_communities = 0
    leaf_prompt_calls = 0             # real run: the same quantity, actually issued

    for level, lvl in enumerate(hierarchy.levels):
        for cid, members in enumerate(lvl.communities):
            if level == 0:
                ids = sorted({
                    chunk for concept in members for chunk in concept_chunks.get(concept, [])
                })
                if max_chunks_per_community is not None:
                    ids = ids[:max_chunks_per_community]
                texts = [t for t in get_chunk_texts(ids) if t and t.strip()] if ids else []
                if not texts:
                    summaries[(level, cid)] = ""
                    skipped_empty += 1
                    continue
                if dry_run:
                    # Measure the SAME batching a real run would do, so the dry run's call count and
                    # prompt sizes reflect the map-reduce rather than one call per community.
                    # ⚠️ This counts the leaf level's PROMPTS — single-batch communities included,
                    # reduce calls excluded. An earlier version named it `planned_leaf_map_calls` and
                    # a test compared it to a real run's `map_calls`; that passed only because the
                    # fixture batched every community, and on the live corpus the plan is 218 while
                    # `map_calls` is 0 (all single-batch). Comparing it to `calls_by_level[0]` is also
                    # wrong — that includes the leaf REDUCE calls. Compare it to `leaf_prompt_calls`.
                    batches, _ = _batch_texts(texts, max_prompt_chars, _overhead(LEAF_PROMPT))
                    planned_leaf_prompts += len(batches)
                    if len(batches) > 1:
                        planned_leaf_batched_communities += 1
                    for batch in batches:
                        prompt_chars_by_level[level] = (
                            prompt_chars_by_level.get(level, 0)
                            + len(LEAF_PROMPT.format(body=SEP.join(batch)))
                        )
                    summaries[(level, cid)] = ""
                    continue
                before = counters["calls"]
                before_chars = counters["prompt_chars"]
                before_prompts = counters["single_calls"] + counters["map_calls"]
                digest = input_digest(texts)
                if checkpoint is not None:
                    hit = checkpoint.lookup(level, cid, digest)
                    if hit is not None:
                        summaries[(level, cid)] = hit
                        continue
                summary = _summarise_with_batching(
                    llm, texts, LEAF_PROMPT, max_prompt_chars, counters,
                    on_call=on_call, where=(level, cid),
                )
                summaries[(level, cid)] = summary
                leaf_prompt_calls += (
                    counters["single_calls"] + counters["map_calls"] - before_prompts
                )
                calls_by_level[level] = calls_by_level.get(level, 0) + (counters["calls"] - before)
                prompt_chars_by_level[level] = (
                    prompt_chars_by_level.get(level, 0)
                    + counters["prompt_chars"] - before_chars
                )
                if checkpoint is not None:
                    # An empty summary is a FAILED community, not a done one — written ok=False so a
                    # resume re-attempts it rather than baking the loss in (§I25).
                    checkpoint.record(level, cid, digest, summary, ok=bool(summary.strip()))
                continue

            # ── parent levels: merge child summaries ──────────────────────────────────────────
            kids = sorted(children.get((level, cid), []))
            parts = [summaries[k] for k in kids if summaries.get(k) and summaries[k].strip()]
            if not parts:
                summaries[(level, cid)] = ""
                # A parent with children has source material — it is only empty because a DRY RUN
                # never generated the child summaries it merges. Counting it as "no source" (the
                # old behaviour) reported 403 parents of the live graph as source-less, which is
                # false and hides the fact that the dry run cannot estimate the parent levels' cost.
                if dry_run and kids:
                    deferred_parents += 1
                else:
                    skipped_empty += 1
                continue
            if dry_run:
                summaries[(level, cid)] = ""
                continue
            before = counters["calls"]
            before_chars = counters["prompt_chars"]
            digest = input_digest(parts)
            if checkpoint is not None:
                hit = checkpoint.lookup(level, cid, digest)
                if hit is not None:
                    summaries[(level, cid)] = hit
                    continue
            summary = _summarise_with_batching(
                llm, parts, PARENT_PROMPT, max_prompt_chars, counters,
                on_call=on_call, where=(level, cid),
            )
            summaries[(level, cid)] = summary
            calls_by_level[level] = calls_by_level.get(level, 0) + (counters["calls"] - before)
            prompt_chars_by_level[level] = (
                prompt_chars_by_level.get(level, 0) + counters["prompt_chars"] - before_chars
            )
            if checkpoint is not None:
                checkpoint.record(level, cid, digest, summary, ok=bool(summary.strip()))

    return {
        "summaries": summaries,
        "calls_by_level": calls_by_level,
        "total_calls": sum(calls_by_level.values()),
        "prompt_chars_by_level": prompt_chars_by_level,
        "skipped_empty": skipped_empty,
        "deferred_parents": deferred_parents,
        "empty_returns": counters["empty_returns"],
        "single_calls": counters["single_calls"],
        "map_calls": counters["map_calls"],
        "reduce_calls": counters["reduce_calls"],
        "batched_communities": counters["batched_communities"],
        "truncated_texts": counters["truncated_texts"],
        "prompt_chars_total": counters["prompt_chars"],
        "planned_leaf_prompts": planned_leaf_prompts,
        "leaf_prompt_calls": leaf_prompt_calls,
        "planned_leaf_batched_communities": planned_leaf_batched_communities,
        # §I53: what a resume saved. `resumed_communities` made NO call, so it is deliberately
        # absent from `total_calls` — the ledger counts spend, not work avoided.
        "resumed_communities": checkpoint.resumed_communities if checkpoint is not None else 0,
        "stale_communities": checkpoint.stale_communities if checkpoint is not None else 0,
        "retried_communities": checkpoint.retried_communities if checkpoint is not None else 0,
        "checkpoint_path": str(checkpoint.path) if checkpoint is not None else None,
    }
