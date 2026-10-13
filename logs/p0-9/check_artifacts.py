"""Post-run sanity check of the Session 3 artifacts."""
import json, collections
from pathlib import Path

root = Path(".")

# ---- step 2 output ----
exp = json.loads((root / "data/eval_queries_gold_expanded.json").read_text())
grew = [q for q in exp if len(q.get("relevant_pages") or []) > 1]
print(f"expanded file: {len(exp)} queries")
print(f"  with >1 relevant page: {len(grew)}  ({len(grew)/len(exp):.0%})")
print(f"  single-page (unchanged): {sum(1 for q in exp if len(q.get('relevant_pages') or []) <= 1)}")
print(f"  max pages on one query: {max(len(q.get('relevant_pages') or []) for q in exp)}")
print("  types:", collections.Counter(q.get("query_type") for q in exp))

# ---- step 3 output ----
neg = json.loads((root / "data/eval_negatives.json").read_text())
print(f"\nnegatives file: {len(neg)} entries")
print("  answerable values:", collections.Counter(n.get("answerable") for n in neg))
print("  ids:", [n["id"] for n in neg][:4], "...")

# ---- verdict cache: what did the judge say for the near_miss queries? ----
cache = root / "data/eval_results/.scan_verdict_cache.jsonl"
by_qid = collections.defaultdict(collections.Counter)
n_lines = 0
for line in cache.read_text().splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        continue
    n_lines += 1
    qid = rec.get("query_id") or rec.get("id")
    by_qid[qid][rec.get("verdict")] += 1

print(f"\nverdict cache: {n_lines} records, {len(by_qid)} query ids")
print("\nper-negative verdict distribution (all pages scanned):")
for n in neg:
    c = by_qid.get(n["id"], collections.Counter())
    tier = n["id"].split("-")[1]
    print(f"  {n['id']:16s} [{tier:8s}] {dict(c)}")
