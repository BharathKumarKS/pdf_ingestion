"""NG-P2 acceptance harness — does the NiceGUI Ask-a-Question path cite the same pages as Streamlit?

The brief's acceptance for NG-P2: *the two runbook queries return answers whose cited pages match
the Streamlit app's on the same queries.*

This harness runs the SAME two queries through BOTH frontends' retrieval+synthesis code and
records, per query, the pages the answer cites:

  * `--side nicegui`   calls `nicegui_app.run_ask` (the function the tab calls via run.io_bound).
  * `--side streamlit --qidx N`  drives the LIVE Streamlit app headlessly with
    `streamlit.testing.v1.AppTest` (set the question, click Search, run) and reads the app's OWN
    "Sources cited" caption.

⚠️ One Streamlit interaction per process: a second `set_value(...).run()` on the same AppTest raises a
session_state KeyError from Streamlit's own harness — hence one query per invocation.

Cited pages are derived by the same regex (`(?:\\[Page\\s*|\\(page\\s*)(\\d+)`) on each side.

Usage:
    .venv/bin/python logs/p1/step10/ng_p2_acceptance.py --side nicegui
    .venv/bin/python logs/p1/step10/ng_p2_acceptance.py --side streamlit --qidx 0
    .venv/bin/python logs/p1/step10/ng_p2_acceptance.py --side streamlit --qidx 1
    .venv/bin/python logs/p1/step10/ng_p2_acceptance.py --compare
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "logs/p1/step10"

QUERIES = [
    # (label, query) — the demo runbook's two verified queries (runbook §3).
    ("factual", "What is Newton's second law?"),
    ("overview",
     "How does Feynman develop the concept of conservation of energy across mechanics, waves and "
     "thermodynamics?"),
]

_CITED_RE = re.compile(r"(?:\[Page\s*|\(page\s*)(\d+)", re.IGNORECASE)
_PSTYLE_RE = re.compile(r"\bp\.\s*(\d+)")
_CHUNK_CAP_RE = re.compile(r"^#\d+.*?\bpage\s+(\d+)", re.IGNORECASE)


def _cited(text: str) -> list[int]:
    return sorted({int(n) for n in _CITED_RE.findall(text or "")})


def _pstyle(text: str) -> list[int]:
    return sorted({int(n) for n in _PSTYLE_RE.findall(text or "")})


def _load_nicegui_module():
    spec = importlib.util.spec_from_file_location("ng_app", ROOT / "src/frontend/nicegui_app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_nicegui(reps: int = 2) -> dict:
    from src.core.config import get_settings
    mod = _load_nicegui_module()
    cfg = get_settings()
    records = []
    for label, q in QUERIES:
        for rep in range(reps):
            t0 = time.time()
            out = mod.run_ask(q, cfg)
            rec = {
                "side": "nicegui",
                "label": label,
                "rep": rep,
                "query": q,
                "wall_s": round(time.time() - t0, 1),
                "intent": out["intent"],
                "answer_chars": len(out["answer"]),
                "answer_head": out["answer"][:400],
                "cited_pages": out["cited_pages"],
                "retrieved_pages": out["retrieved_pages"],
                "n_chunks": len(out["chunks"]),
                "n_raptor": out["n_raptor"],
                "n_graph": out["n_graph"],
            }
            records.append(rec)
            print(f"[nicegui] {label} rep{rep}: cited={rec['cited_pages']} "
                  f"retrieved={len(rec['retrieved_pages'])} intent={rec['intent']} "
                  f"wall={rec['wall_s']}s answer_chars={rec['answer_chars']}")
    return {"side": "nicegui", "records": records}


def run_streamlit(qidx: int) -> dict:
    from streamlit.testing.v1 import AppTest
    label, q = QUERIES[qidx]
    at = AppTest.from_file(str(ROOT / "src/frontend/streamlit_app.py"), default_timeout=900)
    at.run()
    if at.exception:
        raise RuntimeError(f"initial streamlit run raised: {[e.value for e in at.exception]}")
    at.text_area[0].set_value(q)
    at.button[0].click()
    t0 = time.time()
    at.run()
    wall = round(time.time() - t0, 1)
    if at.exception:
        raise RuntimeError(f"search raised: {[e.value for e in at.exception]}")

    # The app's OWN cited-pages line (student branch): "📄 Sources cited: <works> — p. N, p. M".
    src_caption = None
    for cap in at.caption:
        v = cap.value or ""
        if v.startswith("📄 Sources"):
            src_caption = v
            break
    cited = _pstyle(src_caption) if src_caption else []
    # Per-chunk captions in the student "View N source passage(s)" expander:
    #   "#1  *The Feynman Lectures on Physics, Volume I* · page 177"
    retrieved_pages = sorted({int(m) for c in at.caption
                              for m in _CHUNK_CAP_RE.findall(c.value or "")})
    # Fallback/consistency: the longest markdown block that carries page citations (the answer).
    answer_blocks = [m.value for m in at.markdown if _cited(m.value)]
    answer = max(answer_blocks, key=len) if answer_blocks else ""
    rec = {
        "side": "streamlit",
        "label": label,
        "query": q,
        "wall_s": wall,
        "source_caption": src_caption,
        "cited_pages": cited,
        "cited_pages_from_answer": _cited(answer),
        "retrieved_pages": retrieved_pages,
        "answer_chars": len(answer),
        "answer_head": answer[:400],
    }
    print(f"[streamlit] {label}: cited={rec['cited_pages']} "
          f"from_answer={rec['cited_pages_from_answer']} "
          f"retrieved_n={len(retrieved_pages)} wall={wall}s")
    return {"side": "streamlit", "qidx": qidx, "records": [rec]}


def compare() -> dict:
    ng = json.loads((OUT_DIR / "ng_p2_nicegui.json").read_text())
    st = []
    for i in range(len(QUERIES)):
        p = OUT_DIR / f"ng_p2_streamlit_{i}.json"
        st.extend(json.loads(p.read_text())["records"])
    ng_by_label: dict[str, list] = {}
    for r in ng["records"]:
        ng_by_label.setdefault(r["label"], []).append(r)
    st_by_label = {r["label"]: r for r in st}
    rows = []
    for label, _q in QUERIES:
        n_reps = ng_by_label[label]
        s = st_by_label[label]
        n_retrieved = set(n_reps[0]["retrieved_pages"])
        s_retrieved = set(s["retrieved_pages"])
        # Determinism of the NiceGUI retrieval across reps (should be identical).
        retrieved_stable = all(set(r["retrieved_pages"]) == n_retrieved for r in n_reps)
        cited_reps = [sorted(set(r["cited_pages"])) for r in n_reps]
        cited_stable = all(c == cited_reps[0] for c in cited_reps)
        rows.append({
            "label": label,
            "nicegui_cited_reps": cited_reps,
            "nicegui_cited_stable_across_reps": cited_stable,
            "streamlit_cited": s["cited_pages"],
            "cited_sets_equal": set(cited_reps[0]) == set(s["cited_pages"]),
            "nicegui_retrieved_n": len(n_retrieved),
            "streamlit_retrieved_n": len(s_retrieved),
            "retrieved_sets_equal": n_retrieved == s_retrieved,
            "retrieved_stable_across_reps": retrieved_stable,
            "only_nicegui_retrieved": sorted(n_retrieved - s_retrieved),
            "only_streamlit_retrieved": sorted(s_retrieved - n_retrieved),
            "nicegui_intent": n_reps[0]["intent"],
        })
    print(f"\n{'='*74}\nNG-P2 ACCEPTANCE\n{'='*74}")
    for r in rows:
        print(f"\n[{r['label']}]  intent={r['nicegui_intent']}")
        print(f"  cited  nicegui (reps): {r['nicegui_cited_reps']}  "
              f"stable_across_reps={r['nicegui_cited_stable_across_reps']}")
        print(f"  cited  streamlit     : {r['streamlit_cited']}")
        print(f"  cited  sets equal    : {r['cited_sets_equal']}")
        print(f"  retrieved n: nicegui={r['nicegui_retrieved_n']} "
              f"streamlit={r['streamlit_retrieved_n']} "
              f"sets_equal={r['retrieved_sets_equal']} "
              f"nicegui_stable={r['retrieved_stable_across_reps']}")
        if not r["retrieved_sets_equal"]:
            print(f"    only nicegui:   {r['only_nicegui_retrieved']}")
            print(f"    only streamlit: {r['only_streamlit_retrieved']}")
    result = {"rows": rows}
    (OUT_DIR / "ng_p2_acceptance.json").write_text(json.dumps(result, indent=2))
    print(f"\nwrote {OUT_DIR / 'ng_p2_acceptance.json'}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--side", choices=["nicegui", "streamlit", "compare"])
    ap.add_argument("--qidx", type=int, default=0)
    args = ap.parse_args()
    if args.side == "nicegui":
        res = run_nicegui()
        (OUT_DIR / "ng_p2_nicegui.json").write_text(json.dumps(res, indent=2))
        print(f"wrote {OUT_DIR / 'ng_p2_nicegui.json'}")
    elif args.side == "streamlit":
        res = run_streamlit(args.qidx)
        (OUT_DIR / f"ng_p2_streamlit_{args.qidx}.json").write_text(json.dumps(res, indent=2))
        print(f"wrote {OUT_DIR / f'ng_p2_streamlit_{args.qidx}.json'}")
    else:
        compare()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
