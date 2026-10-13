"""Count the eval-query artifacts on disk (ground truth, not from memory)."""
import json
from collections import Counter
from pathlib import Path

files = [
    "data/eval_queries.json",              # legacy v1 (D6: not reused)
    "data/eval_queries_gold.json",         # Session 3 step 1
    "data/eval_queries_gold_expanded.json",# Session 3 step 2 (same queries, widened labels)
    "data/eval_negatives.json",            # Session 3 step 3
]
for f in files:
    p = Path(f)
    if not p.exists():
        print(f"{f:40s} (absent)")
        continue
    d = json.loads(p.read_text())
    types = Counter(x.get("query_type") for x in d)
    print(f"{f:40s} {len(d):4d} entries   types={dict(types)}")
