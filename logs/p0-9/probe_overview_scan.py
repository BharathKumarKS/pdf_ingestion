"""3c: exercise the overview scan path with a stubbed judge (no cluster spend).

Verifies, on the real PDF and the real scan_query:
  * an overview query selects the BOOK-SPANNING judge prompt and the dense stride;
  * the term-bearing sweep judges pages the coarse stride would skip;
  * a factual query is unchanged (standard prompt, default stride).
"""
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location("vec", ROOT / "scripts/validate_eval_calibration.py")
vec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vec)

seen = {"prompts": [], "overview_prompt": False}


def fake_judge(prompt, args, image_b64=None):
    seen["prompts"].append(prompt)
    if "BOOK-SPANNING" in prompt:
        seen["overview_prompt"] = True
    return "YES\npage discusses the topic" if "energy" in prompt.lower() else "NO\nunrelated"


vec.call_judge = fake_judge
vec._get_client = lambda args: None  # the stub never calls it

args = types.SimpleNamespace(
    page_start=1, page_end=80, scan_stride=15, overview_stride=4, scan_window=2,
    workers=4, render_dpi=vec._RENDER_DPI, no_cache=True, cache_file="",
    judge_model="stub-model", judge_backend="openai", judge_api_base="x",
    judge_api_key="", judge_from_env=False,
)
PDF = str(ROOT / "data/base_textbooks/feynman-lectures-on-physics-volume1.pdf")

q = {"id": "ovw-test", "query_type": "overview",
     "query": "Summarize how the book develops the conservation of energy across its chapters."}
hits = vec.scan_query(q, PDF, args)
print("overview judge prompt used :", seen["overview_prompt"], "(must be True)")
print("overview judge calls       :", len(seen["prompts"]))
print("overview key_terms         :", vec.key_terms(q["query"]))
print("overview YES/PARTIAL pages :", sorted(h["page"] for h in hits))

seen["overview_prompt"] = False
seen["prompts"].clear()
q2 = {"id": "fac-test", "query_type": "factual", "query": "What is the speed of light?"}
vec.scan_query(q2, PDF, args)
print("\nfactual used overview prompt:", seen["overview_prompt"], "(must be False)")
print("factual judge calls         :", len(seen["prompts"]))
vec.close_shared_resources()
