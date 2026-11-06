"""Append the architecture diagram pages to the deck PDF (idempotent).

Run AFTER make_demo_deck_pdf.py: that writes demo_deck.pdf as the 13 deck slides; this appends the two
architecture pages (Docs/synapse_architecture_v2.pdf) so the deck PDF always carries the architecture.
Needs pypdf:  uv run --with pypdf python logs/p1/step10/merge_arch_into_deck.py
"""
from pathlib import Path

from pypdf import PdfReader, PdfWriter

REPO = Path(__file__).resolve().parents[3]
DECK = REPO / "logs" / "p1" / "step10" / "demo_deck.pdf"
ARCH = REPO.parent.parent / "Docs" / "synapse_architecture_v2.pdf"

assert DECK.exists(), f"missing {DECK} — run make_demo_deck_pdf.py first"
assert ARCH.exists(), f"missing {ARCH} — render the architecture HTML first"

deck = PdfReader(str(DECK))
arch = PdfReader(str(ARCH))
# guard: the deck must not already carry the architecture (idempotent re-run)
assert len(deck.pages) == 15, f"expected a 15-page deck, got {len(deck.pages)} (already merged?)"

w = PdfWriter()
for p in deck.pages:
    w.add_page(p)
for p in arch.pages:
    w.add_page(p)
with open(DECK, "wb") as f:
    w.write(f)
print(f"merged: {len(deck.pages)} deck + {len(arch.pages)} architecture = {len(w.pages)} pages -> {DECK}")
