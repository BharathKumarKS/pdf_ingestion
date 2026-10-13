"""Inspect the verdict-cache schema and the negative-query verdicts."""
import json, collections
from pathlib import Path

cache = Path("data/eval_results/.scan_verdict_cache.jsonl")
recs = []
for line in cache.read_text().splitlines():
    line = line.strip()
    if line:
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            pass

print("total records:", len(recs))
print("keys of first record:", list(recs[0].keys()))
print("first record:", json.dumps(recs[0], ensure_ascii=False)[:400])

# find the key that looks like a query id
sample = recs[0]
for k, v in sample.items():
    if isinstance(v, str) and ("gold" in v or "neg-" in v):
        print("query-id-like key:", k)

neg = json.loads(Path("data/eval_negatives.json").read_text())
neg_ids = {n["id"] for n in neg}

# group by whichever key holds the query id
qkey = next((k for k, v in sample.items()
             if isinstance(v, str) and v.startswith(("gold", "neg-"))), None)
print("using qkey:", qkey)
by = collections.defaultdict(collections.Counter)
for r in recs:
    qid = (r.get("k") or "").split("|", 1)[0]
    by[qid][r.get("verdict")] += 1

print("\nverdicts for the 24 negatives:")
for nid in sorted(neg_ids):
    print(f"  {nid:16s} {dict(by.get(nid, {}))}")
