"""Independent verifier for the per-query trace module (O2, README Phase 6 cheap half).

Exercises `src/core/query_trace.py` directly — no cluster, no UI. Checks the ring buffer, the stage
timing, the structured log form and the error path. Run:

    .venv/bin/python logs/p1/step10/query_trace_verifier.py
Exit: 0 = all checks pass.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def _fake_time():
    """Deterministic clock: +1.0 unit per perf_counter call (stage = 2 calls = 1000 ms)."""
    class _FT:
        def __init__(self):
            self.t = 0.0

        def perf_counter(self):
            self.t += 1.0
            return self.t
    return _FT()


def run_checks(mod) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    mod.clear()

    # ---- S1/S2/S3 stage timing (deterministic clock) ----
    saved_time = mod.time
    mod.time = _fake_time()
    try:
        with mod.Tracer("q", intent="overview", lanes=["dense", "raptor"], k=20) as tr:
            with tr.stage("embed"):
                pass
            with tr.stage("search"):
                pass
            with tr.stage("search"):
                pass
            tr.set(top1=0.9, n_hits=20)
    finally:
        mod.time = saved_time
    t = tr.trace
    checks["S1 a stage is recorded with elapsed ms > 0"] = (
        "embed" in t.stages_ms and t.stages_ms["embed"] > 0)
    checks["S2 repeated stage names accumulate"] = (
        t.stages_ms.get("search", 0) > 1.5 * t.stages_ms.get("embed", 1e9))
    checks["S3 total_ms >= sum(stages_ms)"] = (
        t.total_ms is not None and t.total_ms >= sum(t.stages_ms.values()) - 1e-6)

    # ---- S4/S5 set() ----
    checks["S4 set() writes a known field"] = t.top1 == 0.9 and t.n_hits == 20
    try:
        tr.set(nope=1)
        checks["S5 set() rejects an unknown field"] = False
    except AttributeError:
        checks["S5 set() rejects an unknown field"] = True

    # ---- S6 record + recent order ----
    mod.clear()
    mod.record(mod.QueryTrace(query="a", intent="factual"))
    mod.record(mod.QueryTrace(query="b", intent="overview"))
    mod.record(mod.QueryTrace(query="c", intent="multihop"))
    r = mod.recent(2)
    checks["S6 recent() returns traces newest-last"] = (
        len(r) == 2 and r[0].query == "b" and r[1].query == "c")

    # ---- S7 buffer cap ----
    mod.clear()
    for i in range(mod.MAX_RECENT + 3):
        mod.record(mod.QueryTrace(query=f"q{i}"))
    capped = mod.recent(mod.MAX_RECENT + 10)
    checks["S7 buffer caps at MAX_RECENT (oldest dropped)"] = (
        len(capped) == mod.MAX_RECENT and capped[0].query == "q3")

    # ---- S8 structured log form ----
    line = mod.QueryTrace(query="x", intent="multihop", lanes=["dense"], k=20,
                          top1=0.5, n_hits=7).as_log()
    try:
        obj = json.loads(line)
        required = {"query", "intent", "lanes", "k", "top1", "n_hits",
                    "stages_ms", "total_ms", "error", "ts"}
        checks["S8 as_log() is JSON with the required keys"] = required <= set(obj)
    except Exception:
        checks["S8 as_log() is JSON with the required keys"] = False

    # ---- S9 error path: stage recorded, error set, exception propagates ----
    mod.clear()
    raised = False
    tr2 = None
    try:
        with mod.Tracer("boom") as tr2:
            with tr2.stage("search"):
                time.sleep(0.002)
                raise ValueError("kaboom")
    except ValueError:
        raised = True
    checks["S9 exception records the stage + error and propagates"] = (
        raised and tr2 is not None and tr2.trace.stages_ms.get("search", 0) > 0
        and tr2.trace.error is not None and "kaboom" in tr2.trace.error)

    # ---- S10 Tracer completion appends to the buffer ----
    mod.clear()
    with mod.Tracer("traced") as tr3:
        pass
    r3 = mod.recent(1)
    checks["S10 Tracer completion appends to the buffer"] = (
        len(r3) == 1 and r3[0].query == "traced" and tr3.trace.total_ms is not None)

    # ---- S11 mark() deltas; S12 start()/finish() (non-CM) ----
    mod.clear()
    saved_time = mod.time
    mod.time = _fake_time()
    try:
        tr4 = mod.Tracer("marked").start()
        tr4.mark("a")
        tr4.mark("b")
        tr4.finish()
    finally:
        mod.time = saved_time
    checks["S11 mark() records the delta since the last mark"] = (
        tr4.trace.stages_ms.get("a", 0) > 0
        and tr4.trace.stages_ms.get("b", 0) <= 1.5 * tr4.trace.stages_ms.get("a", 1e9))
    r4 = mod.recent(1)
    checks["S12 start()/finish() records the trace with total_ms"] = (
        len(r4) == 1 and r4[0].query == "marked" and r4[0].total_ms is not None)

    mod.clear()
    return checks


def main() -> int:
    from src.core import query_trace
    res = run_checks(query_trace)
    npass = sum(1 for ok in res.values() if ok)
    for name, ok in res.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    print(f"\n{npass}/{len(res)} checks PASS")
    return 0 if npass == len(res) else 1


if __name__ == "__main__":
    raise SystemExit(main())
