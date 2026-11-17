#!/usr/bin/env python3
"""V1 — capture the FULL per-query score distribution for BOTH visual modalities. READ-ONLY.

Pre-registration: `.hermes/plans/2026-11-06-p1-visual-lane-aperture-V1V2-preregistration.md`
(committed ALONE, D6.1). V1 captures; V2 (a separate read-only script) derives top1/margin/z and the
per-modality separation verdicts FROM THIS ARTIFACT's raw score arrays.

Local ColPali + Qdrant only — no cluster, no store write, no re-ingest, no src/ change.

Run:  .venv/bin/python logs/p1/step10/visual_aperture_v1.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import numpy as np  # noqa: E402
from loguru import logger  # noqa: E402
from PIL import Image  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.pdf_ingestion.colpali_embedder import get_colpali_embedder  # noqa: E402
from src.pdf_ingestion.store import DocumentStore  # noqa: E402

CURRENT_DOC = "7ba61432-c5e0-416d-aecf-25a232523481"
OLD_IMG_DIR = Path("data/page_images/b2d9fb56-0d83-4355-b3e8-4223946a35b5")
CONCEPT_DIR = Path("logs/p1/step10/concept_images")
VIS_QUERIES = Path("data/eval_queries_v2_visual.json")

IN_DOMAIN_PAGES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 940, 960]
# (stem, text description used ONLY for the text-modality probe, why it is in-domain)
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
FULL_LIMIT = 2001          # the full visual index (2,001 points) — no truncation at the 0.58 default
DEFAULT_THRESHOLD = 0.58   # the shipped default G3 must prove was NOT applied
OUT = Path("logs/p1/step10/visual_aperture_v1.json")


def _visual_points(cfg) -> int | None:
    url = f"http://{cfg.qdrant_host}:{cfg.qdrant_port}/collections/{cfg.colpali_collection}"
    try:
        d = json.load(urllib.request.urlopen(url, timeout=8))
        return d.get("result", {}).get("points_count")
    except Exception as exc:  # pragma: no cover - guard only
        logger.warning("point-count probe failed: {}", exc)
        return None


def main() -> int:
    t0 = time.time()
    cfg = get_settings()
    store = DocumentStore(cfg)
    colpali = get_colpali_embedder(cfg)
    logger.info("colpali = {}", type(colpali).__name__)

    points_before = _visual_points(cfg)
    logger.info("visual index points_before = {}", points_before)

    rows: list[dict] = []
    errors: list[dict] = []

    def _probe_image(modality: str, group: str, label: str, img: Image.Image, meta: dict) -> None:
        try:
            q = colpali.embed_query_image(img.convert("RGB"))
            hits = store.visual_search(query_patches=q, tenant_id=cfg.global_tenant_id,
                                       limit=FULL_LIMIT, score_threshold=0.0)
            rows.append({"modality": modality, "group": group, "label": label,
                         "n_query_patches": int(len(q)), **meta,
                         "scores": [[h.get("page_number"), float(h.get("score_cosine", 0.0))]
                                    for h in hits]})
        except Exception as exc:
            errors.append({"modality": modality, "group": group, "label": label, "error": repr(exc)})
            logger.error("[{}] FAILED: {}", label, exc)

    def _probe_text(group: str, label: str, text: str, meta: dict) -> None:
        try:
            q = colpali.embed_query_text(text)
            hits = store.visual_search(query_patches=q, tenant_id=cfg.global_tenant_id,
                                       limit=FULL_LIMIT, score_threshold=0.0)
            rows.append({"modality": "text", "group": group, "label": label,
                         "n_query_patches": int(len(q)), "text": text, **meta,
                         "scores": [[h.get("page_number"), float(h.get("score_cosine", 0.0))]
                                    for h in hits]})
        except Exception as exc:
            errors.append({"modality": "text", "group": group, "label": label, "error": repr(exc)})
            logger.error("[{}] FAILED: {}", label, exc)

    # ── IMAGE modality ────────────────────────────────────────────────────
    for p in IN_DOMAIN_PAGES:
        f = OLD_IMG_DIR / f"page_{p:04d}.png"
        if f.exists():
            _probe_image("image", "in_book_page", f"book page {p}", Image.open(f),
                         {"expected_page": p, "source": str(f)})
    for stem, _desc, why in CONCEPTS:
        f = CONCEPT_DIR / f"{stem}.png"
        if f.exists():
            _probe_image("image", "in_concept", stem, Image.open(f), {"why": why, "source": str(f)})
    for f in sorted(CONCEPT_DIR.glob("near_*.png")):
        _probe_image("image", "near_domain", f.stem, Image.open(f),
                     {"why": "synthetic figure, topic NOT in Vol 1", "source": str(f)})
    for f in sorted(CONCEPT_DIR.glob("far_*.png")):
        _probe_image("image", "far_domain", f.stem, Image.open(f),
                     {"why": "far: synthetic control", "source": str(f)})
    for label, p, why in OUT_DOMAIN_FILES:
        if Path(p).exists():
            _probe_image("image", "far_domain", label, Image.open(p), {"why": why, "source": p})

    # ── TEXT modality ─────────────────────────────────────────────────────
    for stem, desc, why in CONCEPTS:
        _probe_text("in_concept_text", stem, desc, {"why": why})
    vis = json.loads(VIS_QUERIES.read_text())
    vis = vis if isinstance(vis, list) else vis.get("queries", vis)
    for q in vis:
        _probe_text("vis_query", q.get("id"), q.get("query", ""),
                    {"relevant_pages": q.get("relevant_pages", []), "calibrated": q.get("calibrated")})

    points_after = _visual_points(cfg)

    img_rows = [r for r in rows if r["modality"] == "image"]
    txt_rows = [r for r in rows if r["modality"] == "text"]
    n_img_patches = sorted(r["n_query_patches"] for r in img_rows)
    n_txt_patches = sorted(r["n_query_patches"] for r in txt_rows)
    med_img = n_img_patches[len(n_img_patches) // 2] if n_img_patches else 0
    med_txt = n_txt_patches[len(n_txt_patches) // 2] if n_txt_patches else 0
    all_scores = [s for r in rows for _p, s in r["scores"]]
    below_default = [r for r in rows if any(s < DEFAULT_THRESHOLD for _p, s in r["scores"])]

    guards = {
        "G1_population": (len(img_rows) > 0 and len(txt_rows) == 41),
        "G2_zero_errors": (len(errors) == 0),
        "G3_threshold0_honoured": (len(rows) > 0
                                   and all(len(r["scores"]) > 0 for r in rows)
                                   and len(below_default) == len(rows)),
        "G4_read_only_point_count": (points_before is not None and points_before == points_after),
        "G5_patch_counts_differ": (med_img != med_txt and all(r["n_query_patches"] > 0 for r in rows)),
        "G6_two_modalities_separate": (len(img_rows) > 0 and len(txt_rows) > 0),
    }

    artifact = {
        "meta": {"current_doc": CURRENT_DOC, "full_limit": FULL_LIMIT,
                 "default_threshold": DEFAULT_THRESHOLD, "colpali": type(colpali).__name__,
                 "points_before": points_before, "points_after": points_after,
                 "wall_s": round(time.time() - t0, 1),
                 "n_rows": len(rows), "n_image": len(img_rows), "n_text": len(txt_rows),
                 "median_patches_image": med_img, "median_patches_text": med_txt,
                 "min_score": min(all_scores) if all_scores else None,
                 "max_score": max(all_scores) if all_scores else None},
        "provenance": {
            "in_book_page": "OLD-doc page images (b2d9fb56); a SELF-MATCH test — query image IS the stored vector",
            "in_concept": "SYNTHETIC matplotlib figures, in-domain by TOPIC not appearance (§I107)",
            "text_groups": "in-domain only (concepts + vis-* queries); NO text near/far group (that is V3)",
        },
        "guards": guards,
        "errors": errors,
        "rows": rows,
    }
    OUT.write_text(json.dumps(artifact, indent=1))
    logger.info("wrote {} ({} rows, {} errors, {:.1f}s)", OUT, len(rows), len(errors), time.time() - t0)

    print(f"\nrows={len(rows)} (image {len(img_rows)}, text {len(txt_rows)})  errors={len(errors)}")
    print(f"median patches: image={med_img} text={med_txt}")
    print(f"score range: [{min(all_scores) if all_scores else float('nan'):.4f}, "
          f"{max(all_scores) if all_scores else float('nan'):.4f}]  "
          f"rows with a score < {DEFAULT_THRESHOLD}: {len(below_default)}/{len(rows)}")
    print(f"visual index points: before={points_before} after={points_after}")
    for k, v in guards.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    failed = [k for k, v in guards.items() if not v]
    if failed:
        print(f"GUARD FAILURE: {', '.join(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
