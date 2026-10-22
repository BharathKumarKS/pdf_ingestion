"""`src/pdf_ingestion/entity_resolution.py` — §G3 pure logic, with §I31's four traps pinned.

Each trap has at least one test that FAILS if the trap is re-introduced, because all four are
silent: the merge counts improve while the graph degrades. The names used are the measured ones
from §I31 / the §G3 lever probe.
"""
from __future__ import annotations

from src.pdf_ingestion.entity_resolution import (
    Group,
    build_groups,
    choose_canonical,
    flagged_groups,
    is_formula_like,
    mergeable_groups,
    normalise,
    plan_merges,
    summarise,
)


# ── normalise ─────────────────────────────────────────────────────────────────

def test_normalise_case_articles_parentheticals_plurals():
    assert normalise("Orbit") == "orbit"
    assert normalise("the FDA") == "fda"
    assert normalise("force (vector)") == "force"
    assert normalise("Forces") == "force"
    assert normalise("bodies") == "body"


def test_normalise_does_not_strip_ss():
    # 'ss' must not lose a character: 'stress' -> 'stress', not 'stres'
    assert normalise("stress") == "stress"


# ── T3a: Greek symbols must survive ───────────────────────────────────────────

def test_trap3a_greek_symbols_survive_and_do_not_collapse():
    """A naive [^a-z0-9 ] maps every Greek symbol to '' and merges them into ONE group."""
    names = ["χ (x, t)", "γ", "ħ ω", "π", "ε", "τ", "η", "α"]
    groups, skipped = build_groups(names)
    # Every one must key to something non-empty and distinct — NOT all to one bogus key.
    assert skipped == 0
    keys = {normalise(n) for n in names}
    assert "" not in keys
    assert len(keys) == len(names)          # 8 distinct symbols -> 8 distinct keys
    assert normalise("χ (x, t)") == "χ"
    assert normalise("γ") == "γ"


# ── T3b: the empty key must be COUNTED, not dropped ───────────────────────────

def test_trap3b_single_letter_s_is_counted_not_dropped():
    """The plural rule turns 's' into ''; that must be reported, not silently absorbed."""
    groups, skipped = build_groups(["s", "force", "Force"])
    assert skipped == 1                      # 's' could not be keyed
    assert "" not in groups                  # and it did NOT become a merge key
    # 'force'/'Force' still group correctly
    assert "force" in groups and set(groups["force"].members) == {"force", "Force"}


# ── T1: a formula is not a spelling variant ───────────────────────────────────

def test_trap1_formula_member_flags_the_group_and_is_not_merged():
    names = ["velocity", "Velocity", "Velocity = √(g h)"]
    groups, _ = build_groups(names)
    g = groups["velocity"]
    assert g.formula_members == ["Velocity = √(g h)"]
    assert g.mergeable is False              # flagged, NOT merged
    assert plan_merges(groups) == []         # nothing to merge
    assert [x.key for x in flagged_groups(groups)] == ["velocity"]


def test_trap1_plain_spelling_group_is_still_mergeable():
    names = ["kinetic energy", "Kinetic energy", "Kinetic Energy"]
    groups, _ = build_groups(names)
    plans = plan_merges(groups)
    assert len(plans) == 1
    assert set(plans[0].aliases) | {plans[0].canonical} == set(names)


def test_is_formula_like_examples():
    assert is_formula_like("Velocity = √(g h)")
    assert is_formula_like("E = mc²")
    assert is_formula_like("carbon-14")
    assert not is_formula_like("kinetic energy")
    assert not is_formula_like("Newton's Second Law")


# ── T2: no substring matching ─────────────────────────────────────────────────

def test_trap2_substrings_are_not_grouped():
    """'air' must NOT absorb 'air density' / 'air pressure' — 809 such pairs exist, most distinct."""
    names = ["air", "air density", "air pressure", "air velocity", "absorption",
             "absorption coefficient", "absorption spectrum"]
    groups, _ = build_groups(names)
    assert len(mergeable_groups(groups)) == 0        # no substring-derived merges at all


# ── canonical selection ───────────────────────────────────────────────────────

def test_choose_canonical_prefers_the_most_mentioned_spelling():
    counts = {"temperature": 100, "Temperature": 20}
    assert choose_canonical(["Temperature", "temperature"], counts) == "temperature"


def test_choose_canonical_is_deterministic_without_counts():
    a = choose_canonical(["temperature", "Temperature"])
    b = choose_canonical(["Temperature", "temperature"])
    assert a == b == "temperature"           # shortest, then lexicographic


def test_plan_merges_never_makes_the_canonical_an_alias():
    groups, _ = build_groups(["force", "Force", "forces"])
    for p in plan_merges(groups):
        assert p.canonical not in p.aliases


def test_group_dataclass_mergeable_requires_two_members():
    assert Group(key="x", members=["only"]).mergeable is False
    assert Group(key="x", members=["a", "b"]).mergeable is True


# ── the measurement the G3-0 step asks for ────────────────────────────────────

def test_summarise_counts_empty_keys_and_formula_flags():
    names = ["force", "Force", "s", "velocity", "Velocity = √(g h)", "air", "air density"]
    s = summarise(names)
    assert s["distinct_names"] == 7
    assert s["names_skipped_empty_key"] == 1         # 's'
    assert s["merge_groups"] == 1                    # only force/Force
    assert s["concepts_in_merge_groups"] == 2
    assert s["flagged_formula_groups"] == 1          # velocity + its formula
    assert s["flagged_formula_members"] == 1


def test_summarise_on_the_measured_g3_lever_shape():
    """The rebuilt graph's shape (§I49): the top group is temperature, and it must reproduce."""
    names = ["temperature", "Temperature"] + [f"concept {i}" for i in range(50)]
    s = summarise(names, counts={"temperature": 52, "Temperature": 48})
    plans = plan_merges(build_groups(names)[0], counts={"temperature": 52, "Temperature": 48})
    assert s["merge_groups"] == 1
    assert plans[0].canonical == "temperature"
    assert plans[0].aliases == ["Temperature"]
