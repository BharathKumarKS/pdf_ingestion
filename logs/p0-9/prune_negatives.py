"""Session 3b: prune + re-verify data/eval_negatives.json.

Decision rule, applied from the verdict cache (no judge calls):
  * DROP a negative if a *content* page (not back matter) gets a judge YES — the book
    answers it, so it cannot test abstention.
  * KEEP otherwise. If any content page is a PARTIAL, flag `needs_review` so Session 5
    (human verification) looks at it — a PARTIAL means the book discusses the topic,
    so the negative may be a near-miss rather than genuinely absent.
  * Index-page YESes are capped to PARTIAL by the back-matter gate and never count.
"""
import importlib.util, json
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
    qid, page, _model, _h = r["k"].split("|")
    raw[(qid, int(page))] = r["verdict"]

neg = json.loads((ROOT / "data/eval_negatives.json").read_text())

kept, dropped = [], []
for n in neg:
    qid = n["id"]
    content_yes   = sorted(p for (q, p), v in raw.items() if q == qid and v == "YES" and p < start)
    index_yes     = sorted(p for (q, p), v in raw.items() if q == qid and v == "YES" and p >= start)
    content_part  = sorted(p for (q, p), v in raw.items() if q == qid and v == "PARTIAL" and p < start)

    if content_yes:
        dropped.append((qid, content_yes))
        print(f"DROP   {qid:14s} answered on content pages {content_yes}")
        continue

    tier = qid.split("-")[1]
    note = f"negative ({tier}); term-page re-scan (Session 3b) found no YES page"
    if index_yes:
        note += f"; index-page YES on {index_yes} capped to PARTIAL by back-matter gate"
    entry = dict(n)
    entry["calibration_note"] = note
    if content_part:
        entry["needs_review"] = True
        entry["review_note"] = (
            f"content PARTIAL on {content_part} — the book discusses the topic; "
            "confirm it is genuinely unanswerable (Session 5)"
        )
        print(f"KEEP*  {qid:14s} content PARTIALs {content_part} -> needs_review")
    else:
        print(f"KEEP   {qid:14s} clean")
    kept.append(entry)

out = ROOT / "data/eval_negatives.json"
out.write_text(json.dumps(kept, indent=2, ensure_ascii=False) + "\n")
print(f"\nkept {len(kept)}, dropped {len(dropped)} -> {out}")
store.close()
