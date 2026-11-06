"""Mutation proof for the per-query trace verifier (O2).

Mutates the SOURCE of `src/core/query_trace.py`, loads each mutant as a module, runs the verifier's
`run_checks()` on it, and asserts every mutation reddens >=1 check and every check is reddened by >=1
mutation (no inert check). Does not touch the real file.

Run:  .venv/bin/python logs/p1/step10/query_trace_mutation.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from query_trace_verifier import run_checks  # noqa: E402

SRC = (ROOT / "src" / "core" / "query_trace.py").read_text()
SCRATCH = Path(__file__).resolve().parent / "__qt_mutants__"
SCRATCH.mkdir(exist_ok=True)

_STAGE_LINE = "            self.trace.stages_ms[name] = self.trace.stages_ms.get(name, 0.0) + ms"


def load_mutant(src_text: str, name: str):
    path = SCRATCH / f"{name}.py"
    path.write_text(src_text)
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def mutations():
    yield "MV1 stages do not accumulate", SRC.replace(_STAGE_LINE, "            self.trace.stages_ms[name] = ms")
    yield "MV2 stage not recorded at all", SRC.replace(_STAGE_LINE, "            pass")
    yield "MV4 error never set", SRC.replace(
        "        if exc is not None and self.trace.error is None:", "        if False:")
    yield "MV5 ring buffer has no maxlen", SRC.replace("deque(maxlen=MAX_RECENT)", "deque()")
    yield "MV6 recent() returns oldest-first", SRC.replace(
        "    return items[-n:] if n > 0 else []", "    return items[:n] if n > 0 else []")
    yield "MV7 set() is a no-op", SRC.replace(
        "            setattr(self.trace, key, val)", "            pass")
    yield "MV8 set() does not reject unknown fields", SRC.replace(
        '                raise AttributeError(f"QueryTrace has no field {key!r}")', "                pass")
    yield "MV9 as_log() drops keys", SRC.replace(
        "        return json.dumps(asdict(self), default=str, sort_keys=True)",
        '        return json.dumps({"query": self.query})')
    yield "MV10 total_ms forced to 0", SRC.replace(
        "        self.trace.total_ms = round((time.perf_counter() - self._t0) * 1000, 1)",
        "        self.trace.total_ms = 0.0")
    yield "MV11 mark() does not advance the cursor", SRC.replace(
        "        self._last_mark = now", "        pass")
    yield "MV12 finish() does not record", SRC.replace(
        "        return record(self.trace)", "        return self.trace")


def main() -> int:
    import src.core.query_trace as real
    base = run_checks(real)
    reddened_by: dict[str, int] = {n: 0 for n in base}
    bad = []
    for i, (name, src) in enumerate(mutations()):
        assert src != SRC, f"{name}: substitution did not apply"
        mod = load_mutant(src, f"_qt_mut_{i}")
        res = run_checks(mod)
        newly = [n for n, ok in res.items() if not ok]
        if not newly:
            bad.append(f"{name}: NO check reddened (inert mutation)")
        for n in newly:
            reddened_by[n] += 1
        print(f"  {name:36s} -> reddened {len(newly)}: {', '.join(newly)}")
    inert = [n for n, c in reddened_by.items() if c == 0]
    print("\nchecks reddened by >=1 mutation: "
          f"{sum(1 for c in reddened_by.values() if c)}/{len(reddened_by)}")
    if inert:
        print("INERT CHECKS (never reddened):", inert)
    if bad:
        for b in bad:
            print("  ⚠️", b)
    ok = not inert and not bad
    print("MUTATION PROOF PASS" if ok else "MUTATION PROOF FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
