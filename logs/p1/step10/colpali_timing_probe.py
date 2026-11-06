"""Time the ColPali page-embedding pass (the missing part of a Phase 3 write for the current doc).

Renders N pages from the textbook PDF and times colpali.embed_pages on them, then extrapolates to 968.
Read-only: writes nothing.
"""
import io
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import fitz  # PyMuPDF
from PIL import Image

from src.core.config import get_settings
from src.pdf_ingestion.colpali_embedder import get_colpali_embedder

PDF = "data/base_textbooks/feynman-lectures-on-physics-volume1.pdf"
N = 8
DPI = 150

cfg = get_settings()
print(f"colpali_model={cfg.colpali_model} use_gpu={cfg.use_gpu} "
      f"embedding_batch_size={cfg.embedding_batch_size} colpali_page_batch_size={cfg.colpali_page_batch_size}")

t = time.time()
colpali = get_colpali_embedder(cfg)
_ = colpali.patch_dim
print(f"model load: {time.time()-t:.1f}s")

doc = fitz.open(PDF)
print(f"pdf pages: {doc.page_count}")

t = time.time()
imgs = []
for i in range(100, 100 + N):
    pix = doc[i].get_pixmap(dpi=DPI)
    imgs.append(Image.open(io.BytesIO(pix.tobytes("png"))))
raster = time.time() - t
print(f"rasterize {N} pages @ {DPI}dpi: {raster:.2f}s  ({raster/N:.3f}s/page)")

t = time.time()
mats = colpali.embed_pages(imgs)
embed = time.time() - t
print(f"embed_pages({N}): {embed:.2f}s  ({embed/N:.3f}s/page)  shapes={[tuple(m.shape) for m in mats[:2]]}")

# batch-of-2 behaviour (colpali_page_batch_size=4 -> embed_pages batches at embedding_batch_size//4 = 2)
print(f"\nEXTRAPOLATION to {doc.page_count} pages (CPU, no GPU):")
per_page = embed / N
print(f"  ColPali embed only      : {per_page*doc.page_count/60:.1f} min")
print(f"  + rasterize (approx)    : {(per_page + raster/N)*doc.page_count/60:.1f} min")
print(f"  (Docling re-parse of the whole PDF is EXTRA and not measured here)")
