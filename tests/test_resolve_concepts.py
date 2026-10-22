"""§G3's graph-interaction layer — `read_groups`, `apply_merges`, `sync_concept_embeddings`.

Every test drives a FAKE session that records every statement it is asked to run, so a test can
assert both what happened and what did NOT. The V2 test is the load-bearing one: the naive
implementation `DETACH DELETE`s the alias node and drops its MENTIONS / RELATES_TO /
PREREQUISITE_OF edges with it, and every count in the merge report still improves. Delete
`REPOINT_RELATES` (or any other member of `_ALIAS_STATEMENTS`) and that test fails.
"""
from __future__ import annotations

import json

from src.pdf_ingestion.entity_resolution import (
    DELETE_ALIAS,
    DROP_SELF_RELATES,
    REPOINT_MENTIONS,
    REPOINT_PREREQ_IN,
    REPOINT_PREREQ_OUT,
    REPOINT_RELATES,
    SET_ALIASES,
    MergePlan,
    apply_merges,
    build_groups,
    concept_point_id,
    plan_merges,
    read_groups,
    revert_merges,
    sync_concept_embeddings,
)


# ── fakes ─────────────────────────────────────────────────────────────────────────────────────

class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return self._rows

    def single(self):
        return self._rows[0] if self._rows else None


class FakeSession:
    """Records every statement; answers the reads with canned rows."""

    def __init__(self, groups_rows=None, snapshot=None):
        self.groups_rows = groups_rows or []
        self.snapshot = snapshot or {
            "mentions": [], "relates_to": [], "prerequisite_of": [], "prerequisite_from": [],
        }
        self.statements: list[tuple[str, dict]] = []

    def run(self, cypher, **params):
        self.statements.append((cypher, params))
        if "RETURN k.name AS name" in cypher:
            return FakeResult(self.groups_rows)
        if "RETURN c.id AS chunk" in cypher:
            return FakeResult([{"chunk": c} for c in self.snapshot["mentions"]])
        if "RETURN n.name AS n, r.weight AS w" in cypher:
            return FakeResult(
                [{"n": e["neighbour"], "w": e["weight"]} for e in self.snapshot["relates_to"]]
            )
        if "PREREQUISITE_OF]->(n:Concept)" in cypher:
            return FakeResult([{"n": n} for n in self.snapshot["prerequisite_of"]])
        if "PREREQUISITE_OF]->(k:Concept)" in cypher:
            return FakeResult([{"n": n} for n in self.snapshot["prerequisite_from"]])
        return FakeResult([])

    @property
    def mutations(self):
        """Statements that change the graph — the ones a dry run must never issue."""
        return [
            (c, p) for c, p in self.statements
            if "DELETE" in c or "SET k.aliases" in c or c.startswith("MERGE")
        ]


class FakeQdrant:
    def __init__(self, existing=None):
        self.existing = set(existing or [])
        self.deleted_selector = None
        self.collection = None

    def delete(self, collection_name, points_selector):
        self.collection = collection_name
        self.deleted_selector = points_selector

    def retrieve(self, collection_name, ids):
        return [type("P", (), {"id": i})() for i in ids if i in self.existing]


def _rows(names):
    return [{"name": n, "chunks": [f"{n}-c{i}" for i in range(i + 1)]} for i, n in enumerate(names)]


# ── read_groups ───────────────────────────────────────────────────────────────────────────────

def test_read_groups_builds_groups_and_counts():
    rows = [{"name": "force", "chunks": ["a", "b"]},
            {"name": "Force", "chunks": ["c"]},
            {"name": "Velocity = √(g h)", "chunks": ["d"]}]
    groups, skipped, counts = read_groups(FakeSession(rows), "doc1")
    assert skipped == 0
    assert counts == {"force": 2, "Force": 1, "Velocity = √(g h)": 1}
    assert set(groups["force"].members) == {"force", "Force"}
    assert groups["velocity"].formula_members == ["Velocity = √(g h)"]


def test_read_groups_uses_the_measured_lever_cypher():
    session = FakeSession([])
    read_groups(session, "doc1")
    cypher, params = session.statements[0]
    assert "MATCH (c:Chunk)-[:MENTIONS]->(k:Concept)" in cypher
    assert params == {"doc": "doc1"}


# ── dry run / apply ───────────────────────────────────────────────────────────────────────────

def test_dry_run_issues_no_mutations_and_writes_no_journal(tmp_path):
    session = FakeSession()
    journal = tmp_path / "j.jsonl"
    plans = [MergePlan(canonical="velocity", aliases=["Velocity"], key="velocity")]
    result = apply_merges(session, plans, "doc1", dry_run=True, journal_path=str(journal))
    assert session.mutations == []            # reads only
    assert not journal.exists()               # a dry run leaves no replayable journal
    assert result["aliases_merged"] == 1
    assert result["statements"]               # ...but it still reports what WOULD run


def test_apply_writes_the_journal_only_when_applying(tmp_path):
    session = FakeSession()
    journal = tmp_path / "j.jsonl"
    plans = [MergePlan(canonical="velocity", aliases=["Velocity"], key="velocity")]
    apply_merges(session, plans, "doc1", dry_run=False, journal_path=str(journal))
    entry = json.loads(journal.read_text().strip())
    assert entry["canonical"] == "velocity"
    assert entry["aliases"] == ["Velocity"]
    assert "snapshots" in entry               # the reversibility record


# ── V2: edges are MOVED, not dropped with the node (the load-bearing test) ─────────────────────

def test_v2_edges_are_repointed_before_the_alias_is_dropped():
    session = FakeSession()
    plans = [MergePlan(canonical="velocity", aliases=["Velocity"], key="velocity")]
    stmts = [c for c, _ in apply_merges(session, plans, "doc1", dry_run=False)["statements"]]

    for move in (REPOINT_MENTIONS, DROP_SELF_RELATES, REPOINT_RELATES,
                 REPOINT_PREREQ_OUT, REPOINT_PREREQ_IN):
        assert move in stmts, "an edge move is missing — the alias would be dropped with it"
    assert DELETE_ALIAS in stmts
    # every move must precede the drop, or the edges go with the node
    assert stmts.index(DELETE_ALIAS) > max(stmts.index(m) for m in (
        REPOINT_MENTIONS, DROP_SELF_RELATES, REPOINT_RELATES,
        REPOINT_PREREQ_OUT, REPOINT_PREREQ_IN))


def test_v2_relates_weight_is_summed_not_overwritten():
    """A moved RELATES_TO edge onto an existing edge must ADD its weight (§G3: co-occurrence)."""
    assert "ON MATCH SET nr.weight = nr.weight + r.weight" in REPOINT_RELATES


def test_v1_the_alias_is_recorded_on_the_survivor():
    session = FakeSession()
    plans = [MergePlan(canonical="velocity", aliases=["Velocity", "VELOCITY"], key="velocity")]
    result = apply_merges(session, plans, "doc1", dry_run=False)
    set_stmt = [(c, p) for c, p in result["statements"] if c == SET_ALIASES]
    assert set_stmt and set_stmt[0][1]["aliases"] == ["Velocity", "VELOCITY"]
    # V1's failure mode is a merge that DROPS a name rather than aliasing it
    assert set(result["merges"][0]["aliases"]) == {"Velocity", "VELOCITY"}


# ── reversibility ─────────────────────────────────────────────────────────────────────────────

def test_revert_restores_the_alias_and_its_edges(tmp_path):
    session = FakeSession(snapshot={
        "mentions": ["c1", "c2"],
        "relates_to": [{"neighbour": "force", "weight": 3}],
        "prerequisite_of": ["mass"],
        "prerequisite_from": ["acceleration"],
    })
    journal = tmp_path / "j.jsonl"
    plans = [MergePlan(canonical="velocity", aliases=["Velocity"], key="velocity")]
    apply_merges(session, plans, "doc1", dry_run=False, journal_path=str(journal))

    fresh = FakeSession()
    restored = revert_merges(fresh, str(journal))
    assert restored == 1
    issued = [c for c, _ in fresh.statements]
    assert any("MERGE (a:Concept {name: $name})" in c for c in issued)
    assert any("MERGE (c)-[:MENTIONS]->(a)" in c for c in issued)
    assert any("SET r.weight = $w" in c for c in issued)
    # the snapshot carried the pre-merge weight, so the revert is exact
    w_params = [p for c, p in fresh.statements if "SET r.weight = $w" in c]
    assert w_params[0]["w"] == 3


# ── V6: concept_embeddings sync ───────────────────────────────────────────────────────────────

def test_v6_alias_point_deleted_and_canonical_checked():
    plans = [MergePlan(canonical="velocity", aliases=["Velocity"], key="velocity")]
    client = FakeQdrant(existing=[concept_point_id("velocity")])
    out = sync_concept_embeddings(client, "concept_embeddings", plans, dry_run=False)
    assert out["deleted_alias_points"] == [concept_point_id("Velocity")]
    assert out["missing_canonical_points"] == []
    # the delete used the same uuid5 key the graph build writes
    selector = client.deleted_selector
    assert selector is not None
    assert str(selector.points[0]) == concept_point_id("Velocity")


def test_v6_missing_canonical_point_is_reported():
    plans = [MergePlan(canonical="velocity", aliases=["Velocity"], key="velocity")]
    client = FakeQdrant(existing=[])          # survivor has no point
    out = sync_concept_embeddings(client, "concept_embeddings", plans, dry_run=False)
    assert out["missing_canonical_points"] == [concept_point_id("velocity")]


def test_v6_dry_run_deletes_nothing():
    plans = [MergePlan(canonical="velocity", aliases=["Velocity"], key="velocity")]
    client = FakeQdrant()
    out = sync_concept_embeddings(client, "concept_embeddings", plans, dry_run=True)
    assert client.deleted_selector is None
    assert out["deleted_alias_points"] == [concept_point_id("Velocity")]


# ── the plan is deterministic and never circular ───────────────────────────────────────────────

def test_plan_merges_prefers_the_most_mentioned_spelling():
    groups, _ = build_groups(["temperature", "Temperature"])
    plans = plan_merges(groups, counts={"temperature": 52, "Temperature": 48})
    assert len(plans) == 1
    assert plans[0].canonical == "temperature"
    assert plans[0].aliases == ["Temperature"]
