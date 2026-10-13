"""Per-negative verdict breakdown: raw judge output vs the back-matter gate.

Reads the verdict cache, applies the real gate, and reports for each negative which
pages the judge called YES, which were *capped* (index pages), and which are genuine
content PARTIALs. This is the evidence for the prune decision. No judge calls.
"""
import importlib.util, json, sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("vec", ROOT / "scripts/validate_eval_calibration.py")
vec = importlib.util.module_from_spec(spec); spec.loader.exec_module(vec)

store = vec.PageStore(str(ROOT / "data/base_textbooks/feynman-lectures-on-physics-volume1.pdf"))
start = vec.back_matter_start(store)

raw = {}
for line in (ROOT / "data/eval_results/.scan_verdict_cache.jsonl").read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        r = json.loads(line)
    except json.JSONDecodeError:
        continue
    qid, page, model, _ = r["k"].split("|")
    raw[(qid, int(page))] = (r["verdict"], r.get("reason", ""))

neg = json.loads((ROOT / "data/eval_negatives.json").read_text())
print(f"back_matter_start = {start}\n")
for n in neg:
    qid = n["id"]
    yes_content, yes_capped, partial_content, partial_capped = [], [], [], []
    for (q, p), (v, reason) in raw.items():
        if q != qid:
            continue
        gated = "YES" if (v == "YES" and p >= start) else v
        if v == "YES" and p < start:
            yes_content.append(p)
        elif v == "YES" and p >= start:
            yes_capped.append(p)
        elif v == "PARTIAL" and p < start:
            partial_content.append(p)
        elif v == "PARTIAL" and p >= start:
            partial_capped.append(p)
    verdict = "INVALID (content YES)" if yes_content else (
        "index-only YES" if yes_capped else ("content PARTIALs" if partial_content else "clean"))
    print(f"{qid:14s} {verdict}")
    if yes_content:   print(f"    content YES      : {sorted(yes_content)}")
    if yes_capped:    print(f"    index YES (capped): {sorted(yes_capped)}")
    if partial_content: print(f"    content PARTIAL  : {sorted(partial_content)}")

store.close()
