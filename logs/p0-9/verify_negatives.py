"""Targeted re-verification of the negatives (item 6, cheap path).

For each negative question, judge ONLY the pages that contain its key term(s) plus
+/-2 neighbours — the pages the stride-15 scan never reached. Reuses the same VLM
and the shared verdict cache. Reports any YES/PARTIAL found, i.e. any negative that
is actually answerable.
"""
import argparse, importlib.util, json, sqlite3, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("vec", ROOT / "scripts/validate_eval_calibration.py")
vec = importlib.util.module_from_spec(spec); spec.loader.exec_module(vec)

PDF = "data/base_textbooks/feynman-lectures-on-physics-volume1.pdf"

# Search terms per tier, in seed order (ids are assigned in this order).
TERMS = {
    "out": [
        ["france", "paris"], ["pride and prejudice", "austen"], ["mercury"],
        ["cricket"], ["sourdough", "bread"], ["tokyo"], ["iphone", "apple"],
        ["brazil", "portuguese"],
    ],
    "in_": [
        ["schr", "hydrogen atom"], ["general relativity", "curved space", "curvature of space"],
        ["higgs", "electroweak"], ["entanglement", "bell's theorem", "bell theorem"],
        ["standard model"], ["navier", "viscosity"],
        ["superconduct", "bcs"], ["fourier"],
    ],
    "nea": [
        ["magnetic moment"], ["top quark", "quark"], ["laser"],
        ["carbon-14", "carbon 14", "radiocarbon", "half-life"],
        ["cosmological constant"], ["speed of sound"],
        ["tungsten"], ["jupiter"],
    ],
}

p = argparse.ArgumentParser()
vec.add_scan_args(p); vec.add_judge_args(p)
p.add_argument("--pdf", default=PDF)
args = p.parse_args([
    "--pdf", PDF, "--workers", "8",
    "--judge-backend", "openai",
    "--judge-api-base", "http://10.0.10.70:8000",
    "--judge-model", "Qwen/Qwen3-VL-8B-Instruct",
])
vec.resolve_judge(args)
store = vec._get_page_store(args.pdf, args)
cache = vec._get_verdict_cache(args)

con = sqlite3.connect(ROOT / "data/synapse.db")
neg = json.loads((ROOT / "data/eval_negatives.json").read_text())

print(f"\nTargeted negative re-verification — {len(neg)} negatives, judge={args.judge_model}\n")
flagged = []
for n in neg:
    tier = n["id"].split("-")[1]
    idx = int(n["id"].rsplit("-", 1)[1]) - 1
    terms = TERMS[tier][idx]

    pages = set()
    for t in terms:
        for (pg,) in con.execute(
            "SELECT DISTINCT page_number FROM chunks WHERE lower(text) LIKE ?",
            (f"%{t.lower()}%",),
        ):
            pages.update(range(pg - 2, pg + 3))
    pages = sorted(pg for pg in pages if 1 <= pg <= store.n_pages)

    if not pages:
        print(f"{n['id']:16s} terms={terms}  -> NO term page in the book  => unanswerable OK")
        continue

    store.prewarm(pages)
    res = vec._run_pool(pages, {"id": n["id"], "query": n["query"]}, store, args, cache, args.workers)
    yes = sorted(r["page"] for r in res if r["verdict"] == "YES")
    part = sorted(r["page"] for r in res if r["verdict"] == "PARTIAL")
    verdict = "ANSWERABLE!" if yes else ("partial only" if part else "no YES")
    if yes:
        flagged.append((n["id"], n["query"], yes))
    print(f"{n['id']:16s} terms={terms}")
    print(f"    judged {len(pages)} pages  YES={yes or '-'}  PARTIAL={part or '-'}  -> {verdict}")

con.close()
vec.close_shared_resources()
print(f"\n{'='*70}\nFLAGGED (a YES page exists => the negative is answerable):")
for qid, q, yes in flagged:
    print(f"  {qid}: {q[:70]}  -> pages {yes}")
if not flagged:
    print("  none — no term page answers any negative")
