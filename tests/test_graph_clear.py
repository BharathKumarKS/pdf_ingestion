"""`scripts/clear_graph_document.py` — the clear a graph rebuild must be preceded by.

The script is destructive and its whole job is a scoping decision ("delete THIS document's
graph and no other"), so the tests below pin the two properties that matter:

  * **scope** — every delete is bounded by the document ids the caller passed, and a concept
    a *surviving* document still mentions is never orphaned; and
  * **dry-run safety** — without `--yes` nothing is deleted at all.

They run against a small in-memory graph (`_FakeGraph`) rather than Memgraph, following the
repo's `importlib` script-loading convention (`tests/test_backmatter_gate.py`). The real
Cypher against the real server is exercised by the live dry-run/apply, not here — a fake
cannot validate a query, only the logic that decides what to ask for.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _load_script():
    path = _ROOT / "scripts" / "clear_graph_document.py"
    spec = importlib.util.spec_from_file_location("clear_graph_document_under_test", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves annotations through sys.modules[cls.__module__]; without this the
    # module is not registered and the dataclass decoration raises AttributeError.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cgd = _load_script()


# ── A small graph, and a driver that answers the queries the script issues ────

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def data(self):
        return self._rows

    def single(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, graph):
        self._g = graph

    def run(self, query, **params):
        return _Result(self._g.handle(query, params))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class _FakeGraph:
    """Two documents, with one concept shared between them."""

    def __init__(self, documents=None, chunks=None, mentions=None):
        # document id -> {id, title, tenant}
        self.documents = documents or {}
        # chunk id -> document id
        self.chunks = chunks or {}
        # chunk id -> set of concept names
        self.mentions = mentions or {}
        self.deletes: list[tuple[str, list[str]]] = []
        self.delete_queries: list[str] = []

    def session(self):
        return _Session(self)

    def close(self):
        pass

    # -- query dispatch ------------------------------------------------------
    def handle(self, query: str, params: dict):
        if "DETACH DELETE" in query:
            return self._delete(query, params)
        if "k.name AS n" in query:
            return self._mentioned_names(query, params)
        if "AS id" in query:
            return [dict(d) for d in self.documents.values()]
        if "count(r)" in query:
            return [{"c": self._edge_count(query)}]
        if "count(n)" in query:
            label = query.split("(n:")[1].split(")")[0].split(" ")[0]
            return [{"c": self._node_count(label, params.get("id"))}]
        raise AssertionError(f"fake driver got an unhandled query: {query!r}")

    def _delete(self, query, params):
        # This fake models SCOPED deletes only, and refuses to model an unbounded one. Without
        # this, dropping the `WHERE … IN $ids` clause from a delete would still "pass" every
        # test here, because the fake would go on honouring `params["ids"]` regardless of what
        # the query actually said. The guard is what makes the scope tests real.
        assert "IN $" in query, f"unbounded delete reached the fake: {query!r}"
        self.delete_queries.append(query)
        if "DETACH DELETE c" in query:
            ids = list(params["ids"])
            self.deletes.append(("chunk", ids))
            for cid in [c for c, d in self.chunks.items() if d in ids]:
                del self.chunks[cid]
                self.mentions.pop(cid, None)
        elif "DETACH DELETE p" in query:
            self.deletes.append(("page", list(params["ids"])))
        elif "DETACH DELETE d" in query:
            ids = list(params["ids"])
            self.deletes.append(("document", ids))
            for did in ids:
                self.documents.pop(did, None)
        elif "DETACH DELETE k" in query:
            names = list(params["names"])
            self.deletes.append(("concept", names))
            for cid in self.mentions:
                self.mentions[cid] -= set(names)
        else:
            raise AssertionError(f"unhandled delete: {query!r}")
        return []

    def _mentioned_names(self, query, params):
        ids = params.get("ids")
        if "WHERE NOT (c.document_id IN $ids)" in query:
            keep = {c for c, d in self.chunks.items() if d not in set(ids)}
        elif "WHERE c.document_id IN $ids" in query:
            keep = {c for c, d in self.chunks.items() if d in set(ids)}
        else:
            keep = set(self.chunks)
        names = {n for c in keep for n in self.mentions.get(c, set())}
        return [{"n": n} for n in sorted(names)]

    def _node_count(self, label, doc_id=None):
        if label == "Document":
            return len(self.documents)
        if label == "Chunk":
            return sum(1 for d in self.chunks.values() if d == doc_id)
        if label == "Page":
            return len({self._page_of(c) for c, d in self.chunks.items() if d == doc_id})
        if label == "Concept":
            return len({n for s in self.mentions.values() for n in s})
        raise AssertionError(label)

    def _edge_count(self, query):
        rel = query.split("[r:")[1].split("]")[0]
        if rel == "MENTIONS":
            return sum(len(s) for s in self.mentions.values())
        return 0

    @staticmethod
    def _page_of(chunk_id: str) -> int:
        return int(chunk_id.rsplit("_", 1)[-1])


def _two_documents() -> _FakeGraph:
    """docA: chunks a_1, a_2. docB: chunks b_1, b_2.

    'shared' is mentioned by a_1 (doomed) AND b_1 (surviving) — the case that must NOT be
    orphaned. 'only-a' is mentioned only by docA's chunks; 'only-b' only by docB's.
    """
    return _FakeGraph(
        documents={
            "docA": {"id": "docA", "title": "Doc A", "tenant": "global"},
            "docB": {"id": "docB", "title": "Doc B", "tenant": "global"},
        },
        chunks={"a_1": "docA", "a_2": "docA", "b_1": "docB", "b_2": "docB"},
        mentions={
            "a_1": {"shared", "only-a"},
            "a_2": {"only-a"},
            "b_1": {"shared", "only-b"},
            "b_2": {"only-b"},
        },
    )


# ── Orphan selection ─────────────────────────────────────────────────────────

def test_orphans_are_touched_minus_surviving():
    plan = cgd.ClearPlan(
        requested=["docA"],
        documents=[{"id": "docA"}],
        touched_concepts={"a", "b", "c"},
        surviving_concepts={"c"},
    )
    assert plan.orphans == ["a", "b"]


def test_shared_concept_is_not_orphaned():
    """The bug this guards: subtracting `touched` from ALL mentions would orphan 'shared'."""
    graph = _two_documents()
    plan = cgd.plan_clear(graph, ["docA"])
    assert plan.touched_concepts == {"shared", "only-a"}
    assert plan.surviving_concepts == {"shared", "only-b"}
    assert plan.orphans == ["only-a"]      # 'shared' survives via docB
    assert "shared" not in plan.orphans


# ── Scope ────────────────────────────────────────────────────────────────────

def test_plan_counts_only_the_target_document():
    plan = cgd.plan_clear(_two_documents(), ["docA"])
    assert plan.found_ids == ["docA"]
    assert plan.chunks == 2
    assert plan.pages == 2


def test_apply_clear_deletes_only_the_target_document():
    graph = _two_documents()
    plan = cgd.plan_clear(graph, ["docA"])
    removed = cgd.apply_clear(graph, plan)

    assert removed == {"documents": 1, "chunks": 2, "pages": 2, "concepts": 1}
    # Every DOCUMENT-SCOPED delete is bounded by docA — docB is never named in one. (The
    # concept delete carries names, not ids, and is checked separately below.)
    for kind, ids in graph.deletes:
        if kind == "concept":
            continue
        assert set(ids) <= {"docA"}, f"delete escaped the target scope: {kind} {ids}"
    concept_deletes = [ids for kind, ids in graph.deletes if kind == "concept"]
    assert concept_deletes == [["only-a"]]
    # and docB's graph survives intact
    assert set(graph.documents) == {"docB"}
    assert set(graph.chunks) == {"b_1", "b_2"}
    assert {n for c in graph.chunks for n in graph.mentions[c]} == {"shared", "only-b"}


def test_apply_clear_never_issues_an_unbounded_delete():
    graph = _two_documents()
    plan = cgd.plan_clear(graph, ["docA"])
    cgd.apply_clear(graph, plan)
    kinds = {k for k, _ in graph.deletes}
    assert kinds == {"chunk", "page", "document", "concept"}
    # every delete carries an explicit scope clause — the fake raises if one does not
    assert len(graph.delete_queries) == 4
    assert all("IN $" in q for q in graph.delete_queries)


def test_all_targets_every_document():
    plan = cgd.plan_clear(_two_documents(), ["*"])
    assert sorted(plan.found_ids) == ["docA", "docB"]
    # nothing is outside the doomed set, so every touched concept is orphaned by this clear
    assert plan.orphans == ["only-a", "only-b", "shared"]
    assert plan.touched_concepts == {"shared", "only-a", "only-b"}


def test_unknown_doc_id_is_reported():
    plan = cgd.plan_clear(_two_documents(), ["docA", "nope"])
    assert plan.unknown_ids == ["nope"]


# ── Entry point: dry-run safety and the guards ───────────────────────────────

def test_dry_run_deletes_nothing():
    graph = _two_documents()
    rc = cgd.main(["--doc-id", "docA"], driver=graph)
    assert rc == 0
    assert graph.deletes == []
    assert set(graph.documents) == {"docA", "docB"}


def test_yes_applies_the_clear():
    graph = _two_documents()
    rc = cgd.main(["--doc-id", "docA", "--yes"], driver=graph)
    assert rc == 0
    assert graph.deletes != []
    assert set(graph.documents) == {"docB"}


def test_unknown_doc_id_refuses_and_deletes_nothing():
    graph = _two_documents()
    rc = cgd.main(["--doc-id", "nope", "--yes"], driver=graph)
    assert rc == 2
    assert graph.deletes == []


def test_no_target_is_refused():
    graph = _two_documents()
    assert cgd.main([], driver=graph) == 2
    assert graph.deletes == []


def test_all_and_doc_id_together_are_refused():
    graph = _two_documents()
    assert cgd.main(["--all", "--doc-id", "docA"], driver=graph) == 2
    assert graph.deletes == []


def test_all_clears_the_whole_graph():
    graph = _two_documents()
    rc = cgd.main(["--all", "--yes"], driver=graph)
    assert rc == 0
    assert graph.documents == {}
    assert graph.chunks == {}
    assert graph.mentions == {}
