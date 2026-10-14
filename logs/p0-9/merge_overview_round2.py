"""3c round 2: replace the 8 narrow overview topics with the 9 new book-spanning ones.

Reads the scan-labelled round-2 file, drops the narrow entries from the main overview set,
appends the new ones, and writes the merged set back. Idempotent-ish: refuses to run twice
by checking that the narrow ids are still present.

Run AFTER data/eval_queries_gold_overview_round2_expanded.json exists.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "data/eval_queries_gold_overview_expanded.json"
R2 = ROOT / "data/eval_queries_gold_overview_round2_expanded.json"

# The 8 topics the cheap term-page probe judged narrow (4-15 judged pages), replaced by the
# 9 round-2 topics. Recorded in the pre-registration's Outcome section.
NARROW = ["ovw-018", "ovw-021", "ovw-022", "ovw-023", "ovw-025", "ovw-028", "ovw-032", "ovw-033"]

main = json.loads(MAIN.read_text())
r2 = json.loads(R2.read_text())

missing = [q for q in NARROW if q not in {e["id"] for e in main}]
if missing:
    raise SystemExit(f"already merged? narrow ids absent from the main set: {missing}")
unlabelled = [e["id"] for e in r2 if not e.get("relevant_pages")]
if unlabelled:
    raise SystemExit(f"round-2 entries without labels — scan not finished? {unlabelled}")

kept = [e for e in main if e["id"] not in NARROW]
merged = sorted(kept + r2, key=lambda e: e["id"])
MAIN.write_text(json.dumps(merged, indent=2, ensure_ascii=False))

print(f"main: {len(main)} -> dropped {len(NARROW)} narrow -> +{len(r2)} new = {len(merged)}")
print(f"overview set now: {len(merged)} entries")
for e in merged:
    if e["id"] in {q["id"] for q in r2}:
        print(f"  NEW {e['id']}  {len(e['relevant_pages']):4d} pages  {e['topic']}")
narrow_still = [(e["id"], e["topic"], len(e["relevant_pages"]))
                for e in merged if len(e["relevant_pages"]) <= 15]
print(f"\nstill narrow (<=15 pages): {narrow_still or 'none'}")
