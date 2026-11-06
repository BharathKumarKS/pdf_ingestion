"""Validate the VISUAL lane across three domains, and tune the aperture.

  in_book_page : page images of the SAME PDF stored under the OTHER doc id
                 (data/page_images/b2d9fb56-.../page_NNNN.png). Querying the CURRENT doc's vectors with
                 page N should return page N. A REAL cross-render test (old images Docling-rendered,
                 new ones PyMuPDF@150dpi).
  in_concept   : CONCEPT images of Vol-1 topics -- NOT book pages. The lane's top-5 pages are compared
                 to the TEXT lane's top-5 for the same concept.
  near_domain  : physics-LOOKING but NOT Vol 1 (quantum orbital, EM wave, molecule, stock chart).
                 The adversarial aperture test; should score LOW.
  far_domain   : logos, synthetic noise, a gradient. Trivial controls.

──────────────────────────────────────────────────────────────────────────────────────────────────
PROVENANCE AND LIMITATIONS -- read before trusting any number below.
  * The concept images are SYNTHETIC matplotlib figures (gen_concept_images.py), not photographs and
    not real diagrams. They are faithful depictions of the physics (a real Airy pattern, a real Planck
    curve), but they are RENDERED BY US, so they are easier than real-world images would be.
  * The in_concept GOLD is a PROXY: the TEXT lane's top-5 pages for a description of the concept. It is
    NOT hand-verified ground truth. Overlap therefore measures CROSS-MODAL AGREEMENT, not correctness.
  * The near/far LABELS are our judgement (which topics are in Vol 1). They are stated per image.
  * Every per-query row is printed and written, so nothing is summarised away.
──────────────────────────────────────────────────────────────────────────────────────────────────

Usage:  python logs/p1/step10/visual_lane_validation.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np
from loguru import logger
from PIL import Image

from src.core.config import get_settings
from src.pdf_ingestion.cluster_embedder import get_cluster_embedder
from src.pdf_ingestion.colpali_embedder import get_colpali_embedder
from src.pdf_ingestion.store import DocumentStore

CURRENT_DOC = "7ba61432-c5e0-416d-aecf-25a232523481"
OLD_IMG_DIR = Path("data/page_images/b2d9fb56-0d83-4355-b3e8-4223946a35b5")
CONCEPT_DIR = Path("logs/p1/step10/concept_images")
IN_DOMAIN_PAGES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 940, 960]
# (image stem, text description used ONLY to fetch the text-lane proxy gold, why it is in-domain)
CONCEPTS = [
    ("in_sine_wave", "the sinusoidal wave equation and wave propagation", "Vol1 waves"),
    ("in_two_slit", "two-slit interference fringes", "Vol1 interference"),
    ("in_diffraction_airy", "diffraction of light by a circular aperture", "Vol1 diffraction"),
    ("in_blackbody", "blackbody radiation spectrum and Planck's law", "Vol1 radiation"),
    ("in_pendulum", "the motion of a simple pendulum", "Vol1 mechanics"),
    ("in_resonance", "resonance and the amplitude of a driven oscillator", "Vol1 oscillators"),
    ("in_oscillator", "energy exchange in a harmonic oscillator", "Vol1 oscillators"),
    ("in_energy_ramp", "conservation of energy for a body on a ramp", "Vol1 energy"),
]
# (label, path, why it is near/far domain)
OUT_DOMAIN_FILES = [
    ("logo_poster", "sv_ray_cluster_access/docs/images/logo-poster.png", "far: a brand logo"),
    ("overlapping_logo", "sv_ray_cluster_access/docs/images/overlapping_logo.png", "far: a brand logo"),
    ("phys_img_unknown", "sv_ray_cluster_access/images/phys_img.jpeg", "UNKNOWN: score will classify it"),
]
GRID = [0.0, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]
OUT = Path("logs/p1/step10/visual_lane_validation.json")
TOPK = 5


def main() -> int:
    cfg = get_settings()
    store = DocumentStore(cfg)
    colpali = get_colpali_embedder(cfg)
    dense = get_cluster_embedder(cfg)

    def visual(img):
        q = colpali.embed_query_image(img.convert("RGB"))
        return store.visual_search(query_patches=q, tenant_id=cfg.global_tenant_id, limit=TOPK, score_threshold=0.0)

    def text_pages(query):
        v = np.array(dense.embed_query(query), dtype=np.float32)
        hits = store.search(v, tenant_id=cfg.global_tenant_id, limit=TOPK, query_text=query)
        return [h.get("page_number") for h in hits if h.get("page_number")]

    groups = {}

    rows = []
    for p in IN_DOMAIN_PAGES:
        f = OLD_IMG_DIR / f"page_{p:04d}.png"
        if not f.exists():
            continue
        hits = visual(Image.open(f))
        top = hits[0] if hits else {}
        rows.append({"label": f"book page {p}", "top1_cosine": float(top.get("score_cosine", 0.0)),
                     "top1_page": top.get("page_number"), "expected_page": p,
                     "match": top.get("page_number") == p})
    groups["in_book_page"] = rows

    rows = []
    for name, tq, why in CONCEPTS:
        f = CONCEPT_DIR / f"{name}.png"
        if not f.exists():
            continue
        hits = visual(Image.open(f))
        vpages = [h.get("page_number") for h in hits if h.get("page_number")]
        gpages = text_pages(tq)
        top = hits[0] if hits else {}
        rows.append({"label": name, "why_in_domain": why, "text_query_proxy": tq,
                     "top1_cosine": float(top.get("score_cosine", 0.0)),
                     "visual_pages": vpages, "text_gold_pages": gpages,
                     "overlap": len(set(vpages) & set(gpages)), "text_gold_n": len(set(gpages))})
    groups["in_concept"] = rows

    rows = []
    for f in sorted(CONCEPT_DIR.glob("near_*.png")):
        hits = visual(Image.open(f))
        top = hits[0] if hits else {}
        rows.append({"label": f.stem, "why": "synthetic figure, topic NOT in Vol 1",
                     "top1_cosine": float(top.get("score_cosine", 0.0)), "top1_page": top.get("page_number")})
    groups["near_domain"] = rows

    rows = []
    for name, p, why in OUT_DOMAIN_FILES:
        if Path(p).exists():
            hits = visual(Image.open(p))
            top = hits[0] if hits else {}
            rows.append({"label": name, "why": why, "top1_cosine": float(top.get("score_cosine", 0.0)),
                         "top1_page": top.get("page_number")})
    for f in sorted(CONCEPT_DIR.glob("far_*.png")):
        hits = visual(Image.open(f))
        top = hits[0] if hits else {}
        rows.append({"label": f.stem, "why": "far: synthetic control", "top1_cosine": float(top.get("score_cosine", 0.0)),
                     "top1_page": top.get("page_number")})
    groups["far_domain"] = rows

    # ── report (everything, per row) ──────────────────────────────────────
    print("\n=== in_book_page (page N must return page N) ===")
    for r in groups["in_book_page"]:
        print(f"  {r['label']:14s} cos={r['top1_cosine']:.4f} got={r['top1_page']} exp={r['expected_page']} "
              f"{'MATCH' if r['match'] else 'miss'}")
    print("\n=== in_concept (SYNTHETIC figures; gold = TEXT-lane top-5 PROXY) ===")
    for r in groups["in_concept"]:
        print(f"  {r['label']:20s} cos={r['top1_cosine']:.4f} overlap={r['overlap']}/{r['text_gold_n']} "
              f"visual={r['visual_pages']} text_proxy={r['text_gold_pages']}")
    print("\n=== near_domain (physics-looking, NOT Vol 1 -> should be LOW) ===")
    for r in groups["near_domain"]:
        print(f"  {r['label']:20s} cos={r['top1_cosine']:.4f} top1_page={r['top1_page']}")
    print("\n=== far_domain (controls) ===")
    for r in groups["far_domain"]:
        print(f"  {r['label']:20s} cos={r['top1_cosine']:.4f} top1_page={r['top1_page']}  [{r['why']}]")

    def rate(rows, t):
        return sum(1 for r in rows if r["top1_cosine"] >= t) / len(rows) if rows else 0.0

    print("\n=== APERTURE SWEEP (accept if top-1 cosine >= t) ===")
    hdr = f"{'t':>6} | {'in_book':>8} | {'in_concept':>10} | {'near':>6} | {'far':>6}"
    print(hdr); print("-" * len(hdr))
    sweep = []
    for t in GRID:
        a, b, c, d = (rate(groups["in_book_page"], t), rate(groups["in_concept"], t),
                      rate(groups["near_domain"], t), rate(groups["far_domain"], t))
        sweep.append({"t": t, "in_book": a, "in_concept": b, "near": c, "far": d})
        print(f"{t:>6.2f} | {a:>8.2f} | {b:>10.2f} | {c:>6.2f} | {d:>6.2f}")

    in_all = [r["top1_cosine"] for r in groups["in_book_page"]] + [r["top1_cosine"] for r in groups["in_concept"]]
    in_min = min(in_all) if in_all else 0.0
    near_max = max([r["top1_cosine"] for r in groups["near_domain"]], default=0.0)
    sep = [s["t"] for s in sweep if s["in_book"] == 1.0 and s["in_concept"] == 1.0 and s["near"] == 0.0]
    checks = [
        {"id": "V1 in_book self-page match >= 80%",
         "pass": sum(1 for r in groups["in_book_page"] if r["match"]) / max(1, len(groups["in_book_page"])) >= 0.8},
        {"id": "V2 in_concept mean overlap with text proxy >= 0.4",
         "pass": (sum(r["overlap"] / max(1, r["text_gold_n"]) for r in groups["in_concept"])
                  / max(1, len(groups["in_concept"]))) >= 0.4},
        {"id": "V3 in-domain top-1 min > near-domain top-1 max (separable)",
         "pass": in_min > near_max},
    ]
    print()
    for c in checks:
        print(f"  {'PASS' if c['pass'] else 'FAIL'}  {c['id']}")
    print(f"\n  in-domain top-1 min = {in_min:.4f} | near-domain top-1 max = {near_max:.4f} | gap = {in_min-near_max:+.4f}")
    print(f"  separating thresholds (in=1.0, near=0.0): {sep or 'NONE'}")

    OUT.write_text(json.dumps({
        "provenance": {
            "concept_images": "SYNTHETIC matplotlib figures (gen_concept_images.py), not photographs",
            "in_concept_gold": "TEXT lane top-5 for a description -- a PROXY, not hand-verified ground truth",
            "near_far_labels": "our judgement (which topics are in Vol 1); stated per row",
            "current_doc": CURRENT_DOC,
        },
        "groups": groups, "sweep": sweep, "separating": sep, "checks": checks}, indent=1))
    logger.info("wrote {}", OUT)
    return 0 if all(c["pass"] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
