#!/usr/bin/env python3
"""V3 — build the REAL labelled image set for the visual-lane aperture. No index, no model.

Source of truth: `.hermes/plans/2026-11-06-p1-visual-lane-aperture-SESSIONS.md` §2 (V3) and
`IMPROVEMENTS.md` §I107 / §I123. V1/V2 (score capture + statistic test) are DONE; V3 builds the
labelled set V4 calibrates on and V6 submits from.

Why V3 exists: §I107's test set confounds the question it is meant to answer — the in-domain group
was SYNTHETIC matplotlib plots (in-domain by TOPIC, not appearance) and the near-domain group was
also plots. V3 replaces it with REAL material, split into DISJOINT calibration + held-out halves:

  in_domain   figure crops from the ACTUAL Feynman pages (vector figures, located by drawing bbox)
  near_domain figures from a DIFFERENT physics book (CK-12 "Newton's Three Laws")
  far_domain  brand logos + synthetic noise
  text        the labelled vis-* descriptions (the text modality shares the page embedding space)

Provenance is recorded per item (source file/page, bbox, group, split). The split is DETERMINISTIC
and STRATIFIED per group (alternating by sorted id), so calibration and held-out share no image and
each group is balanced.

Deterministic verification at each stage (exit non-zero on any failure):
  Stage 0  pre-flight / inputs        -> V-0.1 .. V-0.5
  Stage A  in-domain Feynman crops    -> V-A1 .. V-A4
  Stage B  near-domain CK-12 figures  -> V-B1 .. V-B2
  Stage C  far-domain logos + noise   -> V-C1 .. V-C2
  Stage D  split + write              -> V-D1 .. V-D4
  Stage E  manifest + files           -> V-E1 .. V-E4
`--verify-only` re-derives Stage E from the manifest + the files on disk, writing nothing.

Run:  unset PYTHONPATH && .venv/bin/python logs/p1/step10/visual_aperture_v3_set.py
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import fitz  # PyMuPDF
import numpy as np
from loguru import logger
from PIL import Image

FEYNMAN = Path("data/base_textbooks/feynman-lectures-on-physics-volume1.pdf")
CK12 = Path("data/base_textbooks/test_book.pdf")
VIS_QUERIES = Path("data/eval_queries_v2_visual.json")
LOGO_DIR = Path("sv_ray_cluster_access/docs/images")
OUTDIR = Path("logs/p1/step10/visual_aperture_set")
MANIFEST = Path("logs/p1/step10/visual_aperture_v3_set.json")

GAP, MIN_STROKES, MIN_FRAC, MAX_FRAC = 14.0, 3, 0.01, 0.30   # figure-locator quality gate
CROP_DPI = 200
CK12_MIN_DIM = 200          # drop icon-sized embedded images (logos/decorations)
N_NOISE = 6

CHECKS: list[dict] = []


def check(cid: str, ok: bool, detail: str = "") -> bool:
    CHECKS.append({"id": cid, "pass": bool(ok), "detail": detail})
    logger.info("  {}  {}  {}", "PASS" if ok else "FAIL", cid, detail)
    return ok


# ── figure locator (probed on the real PDF before this was written) ───────────

def _inter(a, b) -> float:
    return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0)) * max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))


def _clusters(rects, gap):
    n = len(rects)
    par = list(range(n))

    def find(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    for i in range(n):
        for j in range(i + 1, n):
            a, b = rects[i], rects[j]
            if (a.x0 - gap <= b.x1 and b.x0 - gap <= a.x1
                    and a.y0 - gap <= b.y1 and b.y0 - gap <= a.y1):
                ra, rb = find(i), find(j)
                if ra != rb:
                    par[rb] = ra
    grp: dict[int, list] = {}
    for i in range(n):
        grp.setdefault(find(i), []).append(i)
    out = []
    for idxs in grp.values():
        rs = [rects[i] for i in idxs]
        out.append({"n": len(idxs),
                    "bbox": (min(r.x0 for r in rs), min(r.y0 for r in rs),
                             max(r.x1 for r in rs), max(r.y1 for r in rs))})
    out.sort(key=lambda c: -((c["bbox"][2] - c["bbox"][0]) * (c["bbox"][3] - c["bbox"][1])))
    return out


def locate_figure(page):
    """Return (bbox, n_strokes, area_frac) for the page's best figure cluster, or None."""
    blocks = [fitz.Rect(b[:4]) for b in page.get_text("blocks") if b[6] == 0]
    kept = []
    for g in page.get_drawings():
        r = g["rect"]
        if r.width <= 0 or r.height <= 0:
            continue
        if sum(_inter(r, b) for b in blocks) > 0.6 * (r.width * r.height):
            continue                      # decoration inside text, not a figure stroke
        kept.append(r)
    cs = _clusters(kept, GAP)
    if not cs:
        return None
    c = cs[0]
    x0, y0, x1, y1 = c["bbox"]
    frac = (x1 - x0) * (y1 - y0) / (page.rect.width * page.rect.height)
    return (x0, y0, x1, y1), c["n"], frac


def _figure_pages() -> list[int]:
    qs = json.loads(VIS_QUERIES.read_text())
    qs = qs if isinstance(qs, list) else qs.get("queries", qs)
    return sorted({int(p) for q in qs for p in (q.get("relevant_pages") or [])})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--manifest", default=str(MANIFEST), help="manifest to verify (default: the built one)")
    args = ap.parse_args()

    if args.verify_only:
        return _verify_only(Path(args.manifest))

    # ── Stage 0 — pre-flight ───────────────────────────────────────────────
    logger.info("=== Stage 0 — pre-flight ===")
    for cid, p in [("V-0.1 feynman_pdf", FEYNMAN), ("V-0.2 ck12_pdf", CK12),
                   ("V-0.3 vis_queries", VIS_QUERIES), ("V-0.4 logo_dir", LOGO_DIR)]:
        check(cid, p.exists(), str(p))
    fig_pages = _figure_pages()
    check("V-0.5 figure_pages_found", len(fig_pages) > 0, f"{len(fig_pages)} pages from relevant_pages")
    logger.info("figure pages: {}", fig_pages)

    items: list[dict] = []       # image items
    texts: list[dict] = []       # text items

    # ── Stage A — in-domain: real Feynman figure crops ─────────────────────
    logger.info("=== Stage A — in-domain Feynman figure crops ===")
    doc = fitz.open(FEYNMAN)
    qs = json.loads(VIS_QUERIES.read_text())
    qs = qs if isinstance(qs, list) else qs.get("queries", qs)
    page2q = {}
    for q in qs:
        for p in (q.get("relevant_pages") or []):
            page2q.setdefault(int(p), []).append(q.get("id"))
    n_fail = 0
    for p in fig_pages:
        pg = doc[p - 1]
        loc = locate_figure(pg)
        if loc is None:
            n_fail += 1
            continue
        (x0, y0, x1, y1), n, frac = loc
        if not (MIN_STROKES <= n and MIN_FRAC <= frac <= MAX_FRAC):
            n_fail += 1
            continue
        clip = fitz.Rect(max(0, x0 - 3), max(0, y0 - 3),
                         min(pg.rect.x1, x1 + 3), min(pg.rect.y1, y1 + 3))
        pix = pg.get_pixmap(dpi=CROP_DPI, clip=clip)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        items.append({"id": f"in_domain_p{p:04d}", "group": "in_domain", "modality": "image",
                      "image": img, "source": "feynman", "source_page": p,
                      "bbox": [round(v, 1) for v in clip], "n_strokes": n,
                      "area_frac": round(frac, 4), "source_query_ids": page2q.get(p, []),
                      "why": "real figure crop from the Feynman volume"})
    n_in = len(items)
    check("V-A1 crops_built", n_in >= 20, f"{n_in} crops (dropped {n_fail} of {len(fig_pages)} pages)")
    check("V-A2 crops_nonempty", all(i["image"].width > 20 and i["image"].height > 20 for i in items), "")
    check("V-A3 bbox_within_page", all(0 <= i["bbox"][0] and i["bbox"][2] <= doc[0].rect.x1 for i in items), "")
    check("V-A4 area_frac_in_range", all(MIN_FRAC <= i["area_frac"] <= MAX_FRAC for i in items), "")

    # ── Stage B — near-domain: figures from a DIFFERENT physics book (CK-12) ─
    logger.info("=== Stage B — near-domain CK-12 figures ===")
    ck = fitz.open(CK12)
    for pno in range(ck.page_count):
        pg = ck[pno]
        for im in pg.get_images(full=True):
            xref = im[0]
            try:
                info = ck.extract_image(xref)
            except Exception:  # noqa: BLE001
                continue
            w, h = info.get("width", 0), info.get("height", 0)
            if min(w, h) < CK12_MIN_DIM:
                continue
            img = Image.open(__import__("io").BytesIO(info["image"])).convert("RGB")
            items.append({"id": f"near_domain_ck12_p{pno + 1:02d}_x{xref}", "group": "near_domain",
                          "modality": "image", "image": img, "source": "ck12_test_book",
                          "source_page": pno + 1, "xref": xref, "native_wh": [w, h],
                          "why": "figure from a DIFFERENT physics book (near-domain)"})
    near = [i for i in items if i["group"] == "near_domain"]
    check("V-B1 near_figures_built", len(near) >= 5, f"{len(near)} CK-12 figures (min dim {CK12_MIN_DIM})")
    check("V-B2 near_readable", all(i["image"].width > 0 for i in near), "")

    # ── Stage C — far-domain: brand logos + synthetic noise ────────────────
    logger.info("=== Stage C — far-domain logos + noise ===")
    for f in sorted(list(LOGO_DIR.glob("*.png")) + list(LOGO_DIR.glob("*.jpg")) + list(LOGO_DIR.glob("*.jpeg"))):
        try:
            img = Image.open(f).convert("RGB")
        except Exception:  # noqa: BLE001
            continue
        items.append({"id": f"far_domain_{f.stem}", "group": "far_domain", "modality": "image",
                      "image": img, "source": str(f), "why": "far: a brand logo"})
    rng = np.random.default_rng(1234)
    for i in range(N_NOISE):
        arr = (rng.random((256, 256, 3)) * 255).astype("uint8")
        items.append({"id": f"far_domain_noise_{i:02d}", "group": "far_domain", "modality": "image",
                      "image": Image.fromarray(arr), "source": "synthetic",
                      "why": "far: uniform noise (seeded, reproducible)"})
    far = [i for i in items if i["group"] == "far_domain"]
    check("V-C1 far_items_built", len(far) >= 3, f"{len(far)} far items")
    check("V-C2 far_readable", all(i["image"].width > 0 for i in far), "")

    # ── text modality: the labelled vis-* descriptions ─────────────────────
    for q in qs:
        texts.append({"id": f"text_{q.get('id')}", "group": "text_vis_query", "modality": "text",
                      "text": q.get("query", ""), "source_page": q.get("source_page"),
                      "relevant_pages": q.get("relevant_pages", []),
                      "why": "labelled visual query (text description of a real figure)"})

    # ── Stage D — deterministic stratified split + write ───────────────────
    logger.info("=== Stage D — split + write ===")
    def split_of(group_items):
        for k, it in enumerate(sorted(group_items, key=lambda x: x["id"])):
            it["split"] = "calibration" if k % 2 == 0 else "heldout"

    split_of([i for i in items if i["group"] == "in_domain"])
    split_of([i for i in items if i["group"] == "near_domain"])
    split_of([i for i in items if i["group"] == "far_domain"])
    split_of(texts)

    (OUTDIR / "calibration").mkdir(parents=True, exist_ok=True)
    (OUTDIR / "heldout").mkdir(parents=True, exist_ok=True)
    for it in items:
        d = OUTDIR / it["split"]
        f = d / f"{it['id']}.png"
        it["image"].save(f, "PNG")
        it["file"] = str(f)
        it["sha256"] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        it["written_wh"] = list(it["image"].size)
        del it["image"]           # keep the manifest JSON-serialisable
    logger.info("wrote {} image files under {}", len(items), OUTDIR)

    cal_ids = {i["id"] for i in items if i["split"] == "calibration"}
    held_ids = {i["id"] for i in items if i["split"] == "heldout"}
    cal_sha = {i["sha256"] for i in items if i["split"] == "calibration"}
    held_sha = {i["sha256"] for i in items if i["split"] == "heldout"}
    check("V-D1 split_disjoint", not (cal_sha & held_sha),
          f"same image in both splits: {len(cal_sha & held_sha)}")
    check("V-D2 both_splits_nonempty", len(cal_ids) > 0 and len(held_ids) > 0,
          f"cal={len(cal_ids)} held={len(held_ids)}")
    per_group = {}
    for g in {i["group"] for i in items}:
        gs = [i for i in items if i["group"] == g]
        per_group[g] = {"calibration": sum(1 for i in gs if i["split"] == "calibration"),
                        "heldout": sum(1 for i in gs if i["split"] == "heldout")}
    check("V-D3 each_group_both_splits",
          all(v["calibration"] > 0 and v["heldout"] > 0 for v in per_group.values()), str(per_group))
    check("V-D4 files_on_disk", all(Path(i["file"]).exists() and Path(i["file"]).stat().st_size > 0 for i in items), "")

    # ── Stage E — manifest + provenance completeness ───────────────────────
    logger.info("=== Stage E — manifest ===")
    manifest = {
        "meta": {"feynman": str(FEYNMAN), "ck12": str(CK12), "vis_queries": str(VIS_QUERIES),
                 "crop_dpi": CROP_DPI, "locator": {"gap": GAP, "min_strokes": MIN_STROKES,
                 "min_frac": MIN_FRAC, "max_frac": MAX_FRAC},
                 "n_images": len(items), "n_texts": len(texts),
                 "by_group": {g: sum(1 for i in items if i["group"] == g) for g in per_group},
                 "split_by_group": per_group},
        "images": sorted(items, key=lambda x: x["id"]),
        "texts": sorted(texts, key=lambda x: x["id"]),
        "checks": CHECKS,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=1))
    check("V-E1 manifest_written", MANIFEST.exists(), str(MANIFEST))
    check("V-E2 provenance_complete",
          all(i.get("source") and i.get("group") and i.get("split") and i.get("file") for i in items)
          and all(t.get("group") and t.get("split") and t.get("text") for t in texts), "")
    check("V-E3 in_domain_is_real_crops",
          all(i["source"] == "feynman" and i.get("bbox") and i.get("source_page") for i in items
              if i["group"] == "in_domain"), "")
    check("V-E4 texts_have_relevant_pages",
          all(t.get("relevant_pages") for t in texts), f"{len(texts)} texts")

    return _finish()


def _verify_only(manifest_path: Path) -> int:
    """Re-derive the set's integrity from the manifest + the files on disk. No writes."""
    logger.info("=== --verify-only: re-deriving from manifest + files ===")
    m = json.loads(manifest_path.read_text())
    imgs, txts = m["images"], m["texts"]

    files_ok = all(Path(i["file"]).exists() and Path(i["file"]).stat().st_size > 0 for i in imgs)
    check("R-1 files_present", files_ok, f"{len(imgs)} files")

    hashes_ok = all(hashlib.sha256(Path(i["file"]).read_bytes()).hexdigest()[:16] == i["sha256"] for i in imgs)
    check("R-2 sha256_matches", hashes_ok, "every file re-hashed")

    cal = {i["id"] for i in imgs if i["split"] == "calibration"}
    held = {i["id"] for i in imgs if i["split"] == "heldout"}
    cal_sha = {i["sha256"] for i in imgs if i["split"] == "calibration"}
    held_sha = {i["sha256"] for i in imgs if i["split"] == "heldout"}
    check("R-3 split_disjoint", not (cal_sha & held_sha),
          f"same image content in both splits: {len(cal_sha & held_sha)}")
    check("R-4 both_splits_nonempty", bool(cal) and bool(held), f"cal={len(cal)} held={len(held)}")

    prov_ok = all(i.get("source") and i.get("group") and i.get("split") for i in imgs) \
        and all(t.get("group") and t.get("split") for t in txts)
    check("R-5 provenance_complete", prov_ok, "")

    in_dom = [i for i in imgs if i["group"] == "in_domain"]
    check("R-6 in_domain_real", all(i["source"] == "feynman" and i.get("source_page") for i in in_dom),
          f"{len(in_dom)} in-domain crops")
    return _finish()


def _finish() -> int:
    n_pass = sum(1 for c in CHECKS if c["pass"])
    logger.info("=== {} / {} checks PASS ===", n_pass, len(CHECKS))
    return 0 if n_pass == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
