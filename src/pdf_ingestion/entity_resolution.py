"""§G3 — entity resolution for the concept graph.

The defect (§I2, §I30): near-duplicate `Concept` nodes are separate nodes —
`'orbit'` / `'Orbit'` / `'planetary orbit'` / `"Earth's orbit"` — so a query resolving to one
spelling reaches only that spelling's chunks. Merging a group unions the chunk sets.

This module is the **pure logic** of that merge: normalise a name to a merge key, decide which
groups are safe to merge, and pick a canonical survivor. It does NOT touch Memgraph or Qdrant —
`read_groups` reads the graph, and the apply step lives in the caller. Keeping the decision
separate from the write is what makes it testable without a server, and the write is the part
that must be dry-run first.

THE FOUR TRAPS (§I31), all measured, all designed out here — not caught in review:

  T1  a normalisation group is NOT a synonym set.  `['velocity','Velocity','Velocity = √(g h)']`
      — the third is a FORMULA, not a spelling variant, and merging it into `velocity` is the
      failure the §G plan warns about ("merging two genuinely distinct concepts is worse than
      leaving a duplicate").  → `is_formula_like()` excludes such members; the group is FLAGGED,
      not merged.
  T2  substring matching must NOT be used.  There are 809 normalised substring pairs and most are
      genuinely distinct (`air` ⊂ {air density, air pressure, …}).  → groups are keyed on EQUALITY
      of the normalised key only. There is no substring path in this file.
  T3a punctuation stripping kills physics notation.  A naive `[^a-z0-9 ]` maps every Greek symbol
      to the empty string, collapsing `χ, γ, ħω, π, ε, τ, η, α` into ONE bogus group.
      → the class is Unicode-aware: `[^\\w ]` with `re.UNICODE`.
  T3b the plural rule survives T3a.  A trailing-`s` strip turns the single-letter concept `'s'`
      into `""` — and `""` is a VALID merge key, so it merges whatever else lands there.
      → empty keys are skipped AND counted (`skipped_empty_key`), never silently dropped.
      (Measured on the rebuilt graph: the count is 0 — the `'s'` concept is gone — but the guard
      stays, because the failure is silent and corpus-dependent.)

Design rule from T3: a normaliser must never return a key no name could legitimately produce, and
any name it cannot key must be counted, not dropped. Silence is the failure mode — the merge
counts improve while the graph degrades.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field

# Characters that make a name look like a formula rather than a spelling variant of another name.
# Deliberately broad: a false positive only means a group is flagged for review instead of merged
# automatically, which is the conservative direction (§G3: "merging two genuinely distinct
# concepts is worse than leaving a duplicate").
_FORMULA_CHARS = set("=+−-×÷√^·*/<>≤≥∫ΣΔ")
# An en/em dash and the minus sign are distinct code points from ASCII '-' — all are covered above.


def normalise(name: str) -> str:
    """Normalise a concept name to a merge key.

    Conservative, and NOT substring-based (T2). Unicode-aware so Greek symbols survive (T3a).
    May return "" for a name it cannot key — the caller MUST count those (T3b), never drop them.
    """
    n = name.strip().lower()
    n = re.sub(r"\([^)]*\)", "", n)          # drop parentheticals: "force (vector)" -> "force"
    n = re.sub(r"^(the|a|an)\s+", "", n)     # leading articles: "the FDA" -> "fda"
    # T3a: a Unicode-aware class. `[^a-z0-9 ]` would map every Greek symbol to "".
    n = re.sub(r"[^\w ]+", " ", n, flags=re.UNICODE).replace("_", " ")
    n = re.sub(r"\s+", " ", n).strip()
    if n.endswith("ies"):
        n = n[:-3] + "y"
    elif n.endswith("s") and not n.endswith("ss"):
        n = n[:-1]
    return n


def is_formula_like(name: str) -> bool:
    """True if `name` looks like a formula/expression rather than a spelling variant (T1).

    `'Velocity = √(g h)'` is the measured case: it normalises to `velocity` and would otherwise
    merge into the spelling group.
    """
    if any(ch.isdigit() for ch in name):
        return True
    return any(ch in _FORMULA_CHARS for ch in name)


@dataclass
class Group:
    """One normalised key and the concept names that share it."""

    key: str
    members: list[str] = field(default_factory=list)
    formula_members: list[str] = field(default_factory=list)

    @property
    def mergeable(self) -> bool:
        """A group merges only if it has >1 member and NO formula-like member (T1)."""
        return len(self.members) + len(self.formula_members) > 1 and not self.formula_members

    @property
    def all_members(self) -> list[str]:
        return self.members + self.formula_members


def build_groups(names: list[str]) -> tuple[dict[str, Group], int]:
    """Group concept names by their normalised key.

    Returns (groups, skipped_empty_key). `skipped_empty_key` is RETURNED, not swallowed — a name
    that cannot be keyed must be visible (T3b).
    """
    groups: dict[str, Group] = {}
    skipped_empty_key = 0
    for name in names:
        key = normalise(name)
        if not key:
            skipped_empty_key += 1
            continue
        g = groups.setdefault(key, Group(key=key))
        if is_formula_like(name):
            g.formula_members.append(name)
        else:
            g.members.append(name)
    return groups, skipped_empty_key


def mergeable_groups(groups: dict[str, Group]) -> list[Group]:
    """Only the groups it is safe to merge (T1 applied). Sorted by size, largest first."""
    out = [g for g in groups.values() if g.mergeable]
    out.sort(key=lambda g: (-(len(g.members)), g.key))
    return out


def flagged_groups(groups: dict[str, Group]) -> list[Group]:
    """Groups that would merge but for a formula-like member — for review, never auto-merged."""
    return sorted(
        (g for g in groups.values() if g.formula_members and len(g.all_members) > 1),
        key=lambda g: g.key,
    )


@dataclass
class MergePlan:
    """A canonical survivor and the aliases that fold into it."""

    canonical: str
    aliases: list[str]
    key: str

    def __post_init__(self) -> None:
        # The canonical name must not itself be an alias, or the merge would be circular.
        assert self.canonical not in self.aliases, f"canonical {self.canonical!r} is also an alias"


def choose_canonical(members: list[str], counts: dict[str, int] | None = None) -> str:
    """Pick the survivor for a group.

    Most chunk mentions wins (it is the spelling the corpus actually uses); then the **plain form**
    (the name that already equals its own normalised key — `temperature`, not `Temperature`);
    then the shortest, then lexicographic. Deterministic, so two runs produce the same plan.

    The plain-form tiebreak is load-bearing: a naive lexicographic sort puts the CAPITALISED
    variant first (ASCII `T` < `t`), so the survivor would be the spelling the corpus least uses.
    """
    counts = counts or {}
    return sorted(
        members,
        key=lambda n: (
            -counts.get(n, 0),
            0 if normalise(n) == n else 1,   # the plain form wins ties
            len(n),
            n,
        ),
    )[0]


def plan_merges(groups: dict[str, Group], counts: dict[str, int] | None = None) -> list[MergePlan]:
    """Turn mergeable groups into MergePlans. Formula-bearing groups are skipped (T1)."""
    plans: list[MergePlan] = []
    for g in mergeable_groups(groups):
        canonical = choose_canonical(g.members, counts)
        aliases = [m for m in g.members if m != canonical]
        plans.append(MergePlan(canonical=canonical, aliases=aliases, key=g.key))
    return plans


def summarise(names: list[str], counts: dict[str, int] | None = None) -> dict:
    """The measurement the plan's G3-0 step asks for, on any name list."""
    groups, skipped = build_groups(names)
    merges = plan_merges(groups, counts)
    return {
        "distinct_names": len(names),
        "names_skipped_empty_key": skipped,
        "normalised_keys": len(groups),
        "merge_groups": len(merges),
        "concepts_in_merge_groups": sum(1 + len(p.aliases) for p in merges),
        "share_in_merge_groups": (
            round(sum(1 + len(p.aliases) for p in merges) / len(names), 4) if names else 0.0
        ),
        "flagged_formula_groups": len(flagged_groups(groups)),
        "flagged_formula_members": sum(len(g.formula_members) for g in flagged_groups(groups)),
    }


# ═══════════════════════════════════════════════════════════════════════════════════════════
# §G3's APPLY STEP — read the graph, plan the merges, apply them reversibly.
#
# Kept in this module rather than in a script so the merge DECISION and the merge WRITE are both
# unit-testable against a fake session. Nothing here opens a driver or a Qdrant client of its own:
# every function takes the `session` / `qdrant` it should use.
#
# The write is the dangerous half — it mutates the live graph — so it is dry-run by DEFAULT and
# every merge records enough state to be reverted (`snapshot_alias` / `revert_merges`).
# ═══════════════════════════════════════════════════════════════════════════════════════════


def concept_point_id(name: str) -> str:
    """The Qdrant point id for a concept name — the SAME key the graph build writes.

    `graph_builder._upsert_concepts_to_qdrant` keys `uuid5(NAMESPACE_DNS, f"concept:{name}")`.
    If this ever drifts from that, §G3's sync deletes nothing and V6 fails silently.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"concept:{name}"))


READ_GROUPS_CYPHER = (
    "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept) WHERE c.document_id = $doc "
    "RETURN k.name AS name, collect(DISTINCT c.id) AS chunks"
)


def read_groups(session, document_id: str) -> tuple[dict[str, Group], int, dict[str, int]]:
    """Read a document's Concept names + their chunk mentions, and build the merge groups.

    Returns ``(groups, skipped_empty_key, counts)``. ``counts`` maps a concept name to the number
    of distinct chunks that mention it — it is what `choose_canonical` ranks on (so the survivor is
    the spelling the corpus actually uses) and what the journal records.

    The Cypher mirrors the read-only lever probe (`logs/p1/step10/probe_g3_lever.py`) exactly, so
    the groups this returns are the groups the §G3 lever was measured on.
    """
    rows = session.run(READ_GROUPS_CYPHER, doc=document_id).data()
    names = [r["name"] for r in rows if r.get("name")]
    counts = {r["name"]: len(r.get("chunks") or []) for r in rows if r.get("name")}
    groups, skipped = build_groups(names)
    return groups, skipped, counts


# ── the write: every statement is a module constant, so a test can assert on it ───────────────
#
# The trap this design exists to avoid is V2: an alias's MENTIONS / RELATES_TO / PREREQUISITE_OF
# edges must be MOVED onto the canonical, NOT dropped with the node. A bare `DETACH DELETE` —
# the naive implementation — destroys them, and every count in the merge report still improves.

REPOINT_MENTIONS = (
    "MATCH (c:Chunk)-[m:MENTIONS]->(a:Concept {name: $alias}) "
    "MATCH (k:Concept {name: $canonical}) "
    "MERGE (c)-[:MENTIONS]->(k) DELETE m"
)

# RELATES_TO is undirected and weighted by co-occurrence, so a moved edge must SUM its weight onto
# any edge the canonical already has to the same neighbour — otherwise the merge silently halves a
# weight the ranking reads.
REPOINT_RELATES = (
    "MATCH (a:Concept {name: $alias})-[r:RELATES_TO]-(n:Concept) "
    "WHERE n.name <> $canonical "
    "MATCH (k:Concept {name: $canonical}) "
    "MERGE (k)-[nr:RELATES_TO]-(n) "
    "ON CREATE SET nr.weight = r.weight "
    "ON MATCH SET nr.weight = nr.weight + r.weight "
    "DELETE r"
)

# An edge the alias had to the canonical becomes a self-loop; drop it, never merge it.
DROP_SELF_RELATES = (
    "MATCH (a:Concept {name: $alias})-[r:RELATES_TO]-(k:Concept {name: $canonical}) DELETE r"
)

REPOINT_PREREQ_OUT = (
    "MATCH (a:Concept {name: $alias})-[r:PREREQUISITE_OF]->(b:Concept) "
    "WHERE b.name <> $canonical "
    "MATCH (k:Concept {name: $canonical}) MERGE (k)-[:PREREQUISITE_OF]->(b) DELETE r"
)

REPOINT_PREREQ_IN = (
    "MATCH (b:Concept)-[r:PREREQUISITE_OF]->(a:Concept {name: $alias}) "
    "WHERE b.name <> $canonical "
    "MATCH (k:Concept {name: $canonical}) MERGE (b)-[:PREREQUISITE_OF]->(k) DELETE r"
)

SET_ALIASES = "MATCH (k:Concept {name: $canonical}) SET k.aliases = $aliases"

DELETE_ALIAS = "MATCH (a:Concept {name: $alias}) DETACH DELETE a"

# Every edge move, in the order it must run. DELETE_ALIAS is deliberately NOT here — the caller
# appends it only after all five moves, so the alias is never dropped with its edges still live.
_ALIAS_STATEMENTS = (
    REPOINT_MENTIONS,
    DROP_SELF_RELATES,
    REPOINT_RELATES,
    REPOINT_PREREQ_OUT,
    REPOINT_PREREQ_IN,
)

SNAPSHOT_MENTIONS = (
    "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept {name: $name}) RETURN c.id AS chunk"
)
SNAPSHOT_RELATES = (
    "MATCH (k:Concept {name: $name})-[r:RELATES_TO]-(n:Concept) "
    "RETURN n.name AS n, r.weight AS w"
)
SNAPSHOT_PREREQ_OUT = (
    "MATCH (k:Concept {name: $name})-[:PREREQUISITE_OF]->(n:Concept) RETURN n.name AS n"
)
SNAPSHOT_PREREQ_IN = (
    "MATCH (n:Concept)-[:PREREQUISITE_OF]->(k:Concept {name: $name}) RETURN n.name AS n"
)


def snapshot_alias(session, alias: str) -> dict:
    """Read everything needed to recreate ``alias`` — the reversibility record (V1 / journal).

    Recorded BEFORE any mutation. Without it a merge is one-way: the alias node is gone and its
    chunk mentions and edge weights are unrecoverable, so an unsuccessful §G3 could not be undone.
    """
    mentions = [r["chunk"] for r in session.run(SNAPSHOT_MENTIONS, name=alias).data()]
    relates = [
        {"neighbour": r["n"], "weight": r["w"]}
        for r in session.run(SNAPSHOT_RELATES, name=alias).data()
    ]
    prereq_out = [r["n"] for r in session.run(SNAPSHOT_PREREQ_OUT, name=alias).data()]
    prereq_in = [r["n"] for r in session.run(SNAPSHOT_PREREQ_IN, name=alias).data()]
    return {
        "mentions": mentions,
        "relates_to": relates,
        "prerequisite_of": prereq_out,
        "prerequisite_from": prereq_in,
    }


def apply_merges(session, plans, document_id, dry_run=True, journal_path=None) -> dict:
    """Apply ``MergePlan``s to the graph, re-pointing every edge before the alias is dropped.

    ``dry_run=True`` (the DEFAULT) issues NO writes and writes NO journal — it returns the
    statements that *would* run, which is what a review reads before applying. The journal is
    written only when the merge is actually applied: a dry-run journal that a later revert could
    replay would be a footgun.

    Returns ``{"merges", "statements", "aliases_merged"}``; ``statements`` is the ordered list of
    ``(cypher, params)`` actually issued when applying (and the list that *would* be issued on a
    dry run), so a caller can diff a dry run against the apply.
    """
    statements: list[tuple[str, dict]] = []
    merges: list[dict] = []
    for plan in plans:
        snapshots = {alias: snapshot_alias(session, alias) for alias in plan.aliases}
        merges.append({
            "key": plan.key,
            "canonical": plan.canonical,
            "aliases": list(plan.aliases),
            "snapshots": snapshots,
        })
        for alias in plan.aliases:
            for cypher in _ALIAS_STATEMENTS:
                statements.append((cypher, {"alias": alias, "canonical": plan.canonical}))
            statements.append((DELETE_ALIAS, {"alias": alias, "canonical": plan.canonical}))
        statements.append(
            (SET_ALIASES, {"canonical": plan.canonical, "aliases": list(plan.aliases)})
        )

    if not dry_run:
        for cypher, params in statements:
            session.run(cypher, **params)
        if journal_path:
            with open(journal_path, "a", encoding="utf-8") as fh:
                for merge in merges:
                    fh.write(json.dumps(merge, ensure_ascii=False) + "\n")

    return {
        "merges": merges,
        "statements": statements,
        "aliases_merged": sum(len(m["aliases"]) for m in merges),
    }


def revert_merges(session, journal_path) -> int:
    """Undo the merges recorded in ``journal_path`` — the other half of "reversible".

    Recreates each alias node, restores its chunk mentions and its edges from the snapshot, and
    returns the number of aliases restored. This is what makes §G3's pre-registered rule ("a merge
    that fails V7 is REVERTED, not recorded as a partial success") executable.
    """
    restored = 0
    with open(journal_path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            merge = json.loads(line)
            for alias, snap in merge["snapshots"].items():
                session.run("MERGE (a:Concept {name: $name})", name=alias)
                for chunk in snap["mentions"]:
                    session.run(
                        "MATCH (c:Chunk {id: $chunk}), (a:Concept {name: $alias}) "
                        "MERGE (c)-[:MENTIONS]->(a)",
                        chunk=chunk, alias=alias,
                    )
                for edge in snap["relates_to"]:
                    session.run(
                        "MATCH (a:Concept {name: $alias}), (n:Concept {name: $n}) "
                        "MERGE (a)-[r:RELATES_TO]-(n) SET r.weight = $w",
                        alias=alias, n=edge["neighbour"], w=edge["weight"],
                    )
                for n in snap["prerequisite_of"]:
                    session.run(
                        "MATCH (a:Concept {name: $alias}), (n:Concept {name: $n}) "
                        "MERGE (a)-[:PREREQUISITE_OF]->(n)", alias=alias, n=n,
                    )
                for n in snap["prerequisite_from"]:
                    session.run(
                        "MATCH (a:Concept {name: $alias}), (n:Concept {name: $n}) "
                        "MERGE (n)-[:PREREQUISITE_OF]->(a)", alias=alias, n=n,
                    )
                restored += 1
    return restored


def sync_concept_embeddings(qdrant, collection: str, plans, dry_run=True) -> dict:
    """V6 — delete each merged-away alias's point, and report whether the survivor's exists.

    The point id is `concept_point_id(name)`, the same key the graph build writes. A merge that
    leaves the ANN index holding a name the graph no longer has recreates §G1's measured confound:
    a top-8 seed naming a concept absent from the graph (mean 3.02 of 8 did, pre-merge).
    """
    from qdrant_client.models import PointIdsList

    alias_ids = [concept_point_id(a) for plan in plans for a in plan.aliases]
    canonical_ids = [concept_point_id(p.canonical) for p in plans]
    missing_canonical: list[str] = []
    if not dry_run and alias_ids:
        qdrant.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=alias_ids),  # type: ignore[arg-type]
        )
    if not dry_run and canonical_ids:
        try:
            found = {
                str(p.id) for p in qdrant.retrieve(collection_name=collection, ids=canonical_ids)
            }
            missing_canonical = [pid for pid in canonical_ids if pid not in found]
        except Exception:
            # A client without `retrieve` — report nothing rather than crash the sync.
            missing_canonical = []
    return {
        "deleted_alias_points": alias_ids,
        "canonical_points": canonical_ids,
        "missing_canonical_points": missing_canonical,
    }
