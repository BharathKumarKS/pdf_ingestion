"""Mutation proof for the §I4 LLM-span verifier (O1).

Mutates the SOURCE of `src/core/llm.py` (text substitution), loads each mutant as a module, runs the
verifier's `run_checks()` against it, and asserts: every mutation reddens ≥1 check, and every check
is reddened by ≥1 mutation (no inert check). Does not touch the real file on disk.

Run:  .venv/bin/python logs/p1/step10/llm_span_mutation.py
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from llm_span_verifier import run_checks  # noqa: E402

SRC = (ROOT / "src" / "core" / "llm.py").read_text()
SCRATCH = Path(__file__).resolve().parent / "__llm_mutants__"
SCRATCH.mkdir(exist_ok=True)


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
    yield "MV1 span name wrong", SRC.replace('telemetry.span("llm.call"', 'telemetry.span("llm.wrong"')
    yield "MV2 backend attr key wrong", SRC.replace('{"backend": ', '{"backendX": ')
    yield "MV3 prompt_chars attr key wrong", SRC.replace(
        '"prompt_chars": len(prompt) + len(system)}', '"prompt_charsX": len(prompt) + len(system)}')
    yield "MV4 latency_ms attr key wrong", SRC.replace(
        'telemetry.set_attr(_sp, "latency_ms"', 'telemetry.set_attr(_sp, "latency_msX"')
    yield "MV5 response_chars attr key wrong", SRC.replace(
        'telemetry.set_attr(_sp, "response_chars"', 'telemetry.set_attr(_sp, "response_charsX"')
    yield "MV6 ok attr key wrong", SRC.replace(
        'telemetry.set_attr(_sp, "ok"', 'telemetry.set_attr(_sp, "okX"')
    yield "MV7 return value altered", SRC.replace("    return text\n", '    return text + "!"\n')
    yield "MV8 failure path returns non-empty", SRC.replace(
        '    if body is None:\n        return ""', '    if body is None:\n        return "ERR"')


def main() -> int:
    import src.core.llm as real
    base = run_checks(real)
    reddened_by: dict[str, int] = {n: 0 for n in base}
    bad = []
    for i, (name, src) in enumerate(mutations()):
        assert src != SRC, f"{name}: substitution did not apply"
        mod = load_mutant(src, f"_llm_mut_{i}")
        res = run_checks(mod)
        newly = [n for n, ok in res.items() if not ok]
        if not newly:
            bad.append(f"{name}: NO check reddened (inert mutation)")
        for n in newly:
            reddened_by[n] += 1
        print(f"  {name:34s} -> reddened {len(newly)}: {', '.join(newly)}")
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
