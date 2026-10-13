"""Quick offline check of generate_gold_dataset._extract_questions LaTeX repair."""
import importlib.util

spec = importlib.util.spec_from_file_location("ggd", "scripts/generate_gold_dataset.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

cases = {
    "clean array": '["What is energy?", "Define momentum."]',
    "latex \\( \\) (page-299 failure)":
        '["What quantity replaces \\(m v\\)?","Under what condition does it hold?"]',
    "latex \\frac (must NOT become formfeed)": '["Show that \\frac{1}{2}mv^2 is kinetic energy."]',
    "latex \\theta (must NOT become tab)": '["What is \\theta in the pendulum?"]',
    "latex \\nu (must NOT become newline)": '["What does \\nu denote?"]',
    "latex \\beta (must NOT become backspace)": '["Explain \\beta decay."]',
    "valid escaped quote preserved": '["a \\"quote\\" inside"]',
    "literal backslash preserved": '["a backslash \\\\ here"]',
    "genuinely truncated -> []": '["What is the real part of',
}
for name, raw in cases.items():
    out = m._extract_questions(raw)
    print(f"{name:42s} -> {len(out)} q: {out}")
