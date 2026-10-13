#!/usr/bin/env python3
"""
Independent LLM validation and scan-based calibration of eval_queries.json.

Two modes:

VALIDATE mode (default): validates existing labeled pages.
  For each calibrated query, asks the judge LLM whether each labeled page
  is genuinely relevant. Catches circular calibration (labels drifted toward
  retriever biases). Output flags NO pages that should be removed.

SCAN mode (--scan): finds the right pages from scratch using VLM.
  For each query, scans the PDF in two passes:
    Pass 1 — coarse: checks every Nth page (--scan-stride, default 15) to
              find hot zones (pages scoring YES or PARTIAL).
    Pass 2 — dense: checks all pages in ±scan-window around hot zones.
  Each page is judged from its rendered IMAGE plus its full extracted text
  (D9) — not a truncated text[:800] preview.
  Outputs suggested relevant_pages for each query to update eval_queries.json.
  This is the ground-truth approach — no retriever bias.

RAMP PROBE (--ramp-probe): 100 throwaway page-judgments at concurrency
  1/4/8/16/32, reporting calls/sec and error rate. Run this BEFORE the full
  scan and set --workers to the knee — the gateway batches, and above its
  limit you get queueing or 429/503, not more throughput.

Usage:
    # Validate existing labels
    uv run python scripts/validate_eval_calibration.py \\
        --pdf data/base_textbooks/feynman-lectures-on-physics-volume1.pdf \\
        --judge-backend openai \\
        --judge-api-base http://10.0.10.51:8000 \\
        --judge-model Qwen/Qwen3-VL-8B-Instruct

    # Scan to find correct pages from scratch (slower but unbiased)
    uv run python scripts/validate_eval_calibration.py \\
        --pdf data/base_textbooks/feynman-lectures-on-physics-volume1.pdf \\
        --judge-backend openai \\
        --judge-api-base http://10.0.10.51:8000 \\
        --judge-model Qwen/Qwen3-VL-8B-Instruct \\
        --scan --scan-stride 15 --scan-window 8 \\
        --page-start 30 --page-end 968 --workers 8

    # Take the judge connection from .env instead of the flags
    uv run python scripts/validate_eval_calibration.py ... --scan --judge-from-env

    # Scan only specific queries
    uv run python scripts/validate_eval_calibration.py ... --scan --query-ids vec-002 vec-007

Output: data/eval_results/calibration_validation_<ts>.md (validate)
        data/eval_results/calibration_scan_<ts>.md      (scan)
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf as fitz  # PyMuPDF
import httpx
from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()

# Task 4a: mirrors evaluate_rag.py's _JUDGE_WORKERS. The page list is I/O-bound
# (HTTP waits), so this is a thread pool, not a process pool.
_DEFAULT_WORKERS = 8

# Rendered page resolution. Measured on this machine: dpi=110 → ~12 ms/page and a
# ~119 KB PNG (~113 MB for all 968 pages if every page is touched), which is a
# readable image for the VLM at a size the gateway accepts.
_RENDER_DPI = 110

_DEFAULT_CACHE = "data/eval_results/.scan_verdict_cache.jsonl"

_JUDGE_PROMPT = """\
You are an expert physics educator validating whether a textbook page is \
relevant to a student's question.

Question: {query}

You are shown page {page_number} as an IMAGE (the rendered page) together with \
its extracted text below. Use both — the image carries formulas, figures and \
layout the text extraction may miss.

Page {page_number} text:
---
{page_text}
---

Is this page genuinely useful for answering the question above?
Reply with exactly one of:
  YES   — page directly answers or strongly supports the question
  PARTIAL — page is related but only partially relevant
  NO    — page does not meaningfully help answer the question

Then on the next line, one sentence explaining why.
Reply format (two lines only):
<YES|PARTIAL|NO>
<one sentence reason>"""


# ── Page access: one open PDF, each page rendered/extracted once (Task 4a #1) ───

class PageStore:
    """One open PDF handle; per-page text and rendered image cached once.

    Replaces the old ``extract_page_text()``, which called ``fitz.open()`` on the
    whole 968-page PDF on *every* page judgement — roughly 33,000 opens over a full
    two-pass scan. PyMuPDF documents are not thread-safe, so all document access is
    serialised behind one lock; the HTTP calls (the actual wait) stay concurrent.
    """

    def __init__(self, pdf_path: str, dpi: int = _RENDER_DPI):
        self.pdf_path = pdf_path
        self.dpi = dpi
        self._doc = fitz.open(pdf_path)
        self.n_pages = len(self._doc)
        self._text: dict[int, str] = {}
        self._img: dict[int, str | None] = {}
        self._lock = threading.Lock()

    def text(self, page_number: int) -> str:
        with self._lock:
            if page_number in self._text:
                return self._text[page_number]
        if page_number < 1 or page_number > self.n_pages:
            return f"[page {page_number} out of range — PDF has {self.n_pages} pages]"
        try:
            with self._lock:
                raw = str(self._doc[page_number - 1].get_text("text")).strip()
        except Exception as exc:  # noqa: BLE001 - one bad page must not kill the scan
            logger.warning("Text extraction failed for page {}: {}", page_number, exc)
            raw = ""
        text = raw or "[no text extracted]"
        with self._lock:
            self._text[page_number] = text
        return text

    def image_b64(self, page_number: int) -> str | None:
        """PNG of the page, base64 (no data: prefix). None if it cannot be rendered."""
        with self._lock:
            if page_number in self._img:
                return self._img[page_number]
        b64 = None
        if 1 <= page_number <= self.n_pages:
            try:
                with self._lock:
                    pix = self._doc[page_number - 1].get_pixmap(dpi=self.dpi)
                b64 = base64.b64encode(pix.tobytes("png")).decode("ascii")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Page render failed for page {}: {}", page_number, exc)
        with self._lock:
            self._img[page_number] = b64
        return b64

    def prewarm(self, pages) -> None:
        """Render + extract a page list once, before the parallel wave.

        Keeps the render cost out of the threads, where it would serialise behind the
        document lock anyway.
        """
        for p in pages:
            self.text(p)
            self.image_b64(p)

    def close(self) -> None:
        with self._lock:
            self._doc.close()


# ── Verdict cache on disk: resume + bit-identical re-runs (Task 4a #2) ──────────

class VerdictCache:
    """Append-only JSONL cache of judge verdicts.

    Keyed by (query_id, page, model, prompt-hash). The prompt hash means the cache
    invalidates itself whenever the judge prompt changes (e.g. adding the page
    image), so a stale verdict can never be served for a different question.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._mem: dict[str, dict] = {}
        self.hits = 0
        self.misses = 0
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    self._mem[rec["k"]] = {"verdict": rec["verdict"], "reason": rec.get("reason", "")}
                except (json.JSONDecodeError, KeyError, TypeError):
                    continue
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(query_id: str, page: int, model: str, prompt: str) -> str:
        h = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:16]
        return f"{query_id}|{page}|{model}|{h}"

    def get(self, key: str) -> dict | None:
        with self._lock:
            hit = self._mem.get(key)
            if hit is None:
                self.misses += 1
                return None
            self.hits += 1
            return dict(hit)

    def put(self, key: str, entry: dict) -> None:
        with self._lock:
            if key in self._mem:
                return
            self._mem[key] = dict(entry)
            with self.path.open("a") as fh:
                fh.write(json.dumps({"k": key, **entry}, ensure_ascii=False) + "\n")


# ── Shared process-wide resources ──────────────────────────────────────────────

_STORES: dict[tuple, PageStore] = {}
_CACHES: dict[str, VerdictCache] = {}
_CLIENT: httpx.Client | None = None
_CLIENT_KEY: tuple | None = None
_LOCK = threading.Lock()


def _get_page_store(pdf_path: str, args) -> PageStore:
    key = (str(Path(pdf_path).resolve()), getattr(args, "render_dpi", _RENDER_DPI))
    with _LOCK:
        store = _STORES.get(key)
        if store is None:
            store = PageStore(key[0], key[1])
            _STORES[key] = store
        return store


def _get_verdict_cache(args) -> VerdictCache:
    path = str(getattr(args, "cache_file", _DEFAULT_CACHE) or _DEFAULT_CACHE)
    with _LOCK:
        cache = _CACHES.get(path)
        if cache is None:
            cache = VerdictCache(Path(path))
            _CACHES[path] = cache
        return cache


def _get_client(args) -> httpx.Client:
    """One shared httpx.Client for the whole run (Task 4a #4).

    Module-level ``httpx.post`` opened a new connection per call, so every one of the
    ~25k judgements paid a TCP + TLS handshake.
    """
    global _CLIENT, _CLIENT_KEY
    key = (args.judge_backend, args.judge_api_base, args.judge_api_key, args.judge_model)
    with _LOCK:
        if _CLIENT is None or _CLIENT_KEY != key:
            if _CLIENT is not None:
                _CLIENT.close()
            workers = max(4, int(getattr(args, "workers", _DEFAULT_WORKERS)))
            _CLIENT = httpx.Client(
                timeout=httpx.Timeout(120.0, connect=10.0),
                limits=httpx.Limits(max_connections=workers * 2,
                                    max_keepalive_connections=workers),
            )
            _CLIENT_KEY = key
        return _CLIENT


def close_shared_resources() -> None:
    global _CLIENT
    with _LOCK:
        if _CLIENT is not None:
            _CLIENT.close()
            _CLIENT = None
        for store in _STORES.values():
            store.close()
        _STORES.clear()


def resolve_judge(args) -> None:
    """Fill the judge connection from .env for any judge field left empty.

    The judge must not be the generator: a model scoring its own output grades itself
    preferentially, so the number stops measuring anything. ``JUDGE_MODEL`` therefore
    takes precedence over the generator model, and we say so loudly when it is unset.
    """
    need = (getattr(args, "judge_from_env", False)
            or not getattr(args, "judge_model", "")
            or not getattr(args, "judge_api_base", ""))
    if not need:
        return
    from src.core.config import get_settings
    cfg = get_settings()
    if cfg.llm_backend == "ollama":
        args.judge_backend = "ollama"
        args.judge_api_base = cfg.ollama_host
        args.judge_model = cfg.judge_model or cfg.ollama_model
    else:
        args.judge_backend = "openai"
        args.judge_api_base = cfg.openai_api_base
        args.judge_api_key = cfg.openai_api_key
        args.judge_model = cfg.judge_model or cfg.openai_model
    if not cfg.judge_model:
        logger.warning(
            "JUDGE_MODEL is unset — judging with the generator model ({}). A model "
            "scoring its own output is not a measurement (ARCHITECTURE.md trap 18).",
            args.judge_model,
        )
    console.print(f"Judge from env: [cyan]{args.judge_backend}[/] / [cyan]{args.judge_model}[/]")


# ── Judge call ─────────────────────────────────────────────────────────────────

def call_judge(prompt: str, args, image_b64: str | None = None) -> str:
    """Call the judge LLM (text + optional page image) and return raw response text."""
    client = _get_client(args)
    if args.judge_backend == "anthropic":
        content: list[dict] = []
        if image_b64:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png", "data": image_b64},
            })
        content.append({"type": "text", "text": prompt})
        payload = {
            "model": args.judge_model,
            "max_tokens": 512,
            "messages": [{"role": "user", "content": content}],
        }
        resp = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": args.judge_api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        blocks = resp.json().get("content") or []
        text = "".join(
            (block.get("text") or "")
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
        return text.strip()

    else:  # openai-compatible
        headers = {"Content-Type": "application/json"}
        # Mirror llm.py: the cluster gateway returns HTTP 500 for an empty
        # `Authorization:` header, so omit it entirely when unset.
        key = (args.judge_api_key or "").strip()
        if key and key.lower() != "none":
            headers["Authorization"] = f"Bearer {key}"
        base = args.judge_api_base.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        content = []
        if image_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{image_b64}"},
            })
        content.append({"type": "text", "text": prompt})
        payload = {
            "model": args.judge_model,
            "max_tokens": 512,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "You are a physics expert validating textbook page relevance."},
                {"role": "user", "content": content},
            ],
        }
        resp = client.post(f"{base}/v1/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        # Reasoning models emit content=null when the token budget went on reasoning;
        # fall back so the verdict is not silently empty.
        return ((msg.get("content") or "").strip()
                or (msg.get("reasoning") or "").strip())


def parse_verdict(response: str) -> tuple[str, str]:
    """Parse judge response into (verdict, reason). Strips  thinking blocks."""
    import re
    # Strip chain-of-thought blocks (DeepSeek R1, Qwen3 thinking mode)
    cleaned = re.sub(r" thinking.*?</think>", "", response, flags=re.DOTALL).strip()
    lines = [l.strip() for l in cleaned.splitlines() if l.strip()]
    verdict = "UNKNOWN"
    reason = cleaned[:120]
    if lines:
        first = lines[0].upper()
        if first.startswith("YES"):
            verdict = "YES"
        elif first.startswith("PARTIAL"):
            verdict = "PARTIAL"
        elif first.startswith("NO"):
            verdict = "NO"
        reason = lines[1] if len(lines) > 1 else lines[0]
    return verdict, reason


def _judge_page(query: dict, page_num: int, store: PageStore, args, cache: VerdictCache | None) -> dict:
    """Judge one page for one query, with disk caching and a bounded retry."""
    text = store.text(page_num)
    prompt = _JUDGE_PROMPT.format(
        query=query["query"], page_number=page_num, page_text=text,
    )
    key = VerdictCache.key(query["id"], page_num, args.judge_model, prompt)
    if cache is not None:
        hit = cache.get(key)
        if hit is not None:
            return {"page": page_num, **hit, "cached": True}

    image = store.image_b64(page_num)
    verdict, reason = "ERROR", ""
    for attempt in range(1, 4):
        try:
            raw = call_judge(prompt, args, image)
            verdict, reason = parse_verdict(raw)
            break
        except Exception as exc:  # noqa: BLE001
            reason = f"{type(exc).__name__}: {exc}"[:120]
            if attempt < 3:
                time.sleep(min(2 ** attempt, 8))
            else:
                logger.error("Judge call failed for {} p{} after 3 attempts: {}",
                             query["id"], page_num, reason)

    entry = {"verdict": verdict, "reason": reason}
    # Errors are deliberately not cached: a resumed run should retry them.
    if cache is not None and verdict != "ERROR":
        cache.put(key, entry)
    return {"page": page_num, **entry}


def _run_pool(pages: list[int], query: dict, store: PageStore, args,
              cache: VerdictCache | None, workers: int) -> list[dict]:
    """Judge a page list concurrently; returns results sorted by page."""
    if not pages:
        return []
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_judge_page, query, p, store, args, cache): p for p in pages}
        for fut in as_completed(futures):
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001
                results.append({"page": futures[fut], "verdict": "ERROR", "reason": str(exc)[:120]})
    results.sort(key=lambda r: r["page"])
    return results


def validate_query(query: dict, store: PageStore, args) -> list[dict]:
    """Validate all labeled pages for one query. Returns list of page verdicts."""
    cache = _get_verdict_cache(args)
    results = []
    for page_num in (query.get("relevant_pages") or []):
        r = _judge_page(query, page_num, store, args, cache)
        results.append({
            "page": r["page"],
            "verdict": r["verdict"],
            "reason": r["reason"],
            "text_preview": store.text(r["page"])[:120].replace("\n", " "),
        })
        icon = {"YES": "✓", "PARTIAL": "~", "NO": "✗", "ERROR": "!", "UNKNOWN": "?"}.get(r["verdict"], "?")
        console.print(f"    p{page_num}: [{icon}] {r['verdict']} — {r['reason'][:70]}")
    return results


def scan_query(query: dict, pdf_path: str, args) -> list[dict]:
    """
    Two-pass scan to find relevant pages for a query without any prior labels.
    Pass 1: coarse scan every scan_stride pages → find hot zones.
    Pass 2: dense scan all pages within scan_window of each hot zone.
    Returns list of {page, verdict, reason} for YES/PARTIAL hits.

    Both passes run over a thread pool (Task 4a #3). Pass 2 re-uses pass 1's hot-page
    verdicts instead of re-judging them — the old code judged each hot page twice.
    """
    store = _get_page_store(pdf_path, args)
    cache = _get_verdict_cache(args)
    workers = max(1, int(getattr(args, "workers", _DEFAULT_WORKERS)))

    # getattr defaults so a minimal args namespace (the Task 4 / Task 5 tools) drives
    # the same scan as this script's own CLI.
    start  = max(int(getattr(args, "page_start", 30)), 1)
    end    = min(int(getattr(args, "page_end", 968)), store.n_pages)
    stride = int(getattr(args, "scan_stride", 15))
    window = int(getattr(args, "scan_window", 8))

    # Pass 1: coarse
    coarse_pages = list(range(start, end + 1, stride))
    console.print(f"  Pass 1 — coarse (every {stride} pages, {start}-{end}, "
                  f"{len(coarse_pages)} pages, {workers} workers)…")
    store.prewarm(coarse_pages)
    pass1 = _run_pool(coarse_pages, query, store, args, cache, workers)

    hot_pages = {r["page"] for r in pass1 if r["verdict"] in ("YES", "PARTIAL")}
    for r in pass1:
        if r["verdict"] in ("YES", "PARTIAL"):
            icon = {"YES": "[green]✓[/]", "PARTIAL": "[yellow]~[/]"}[r["verdict"]]
            console.print(f"    p{r['page']}: {icon} {r['verdict']} — {r['reason'][:60]}")

    if not hot_pages:
        console.print("  [yellow]No hot zones found in coarse pass.[/]")
        return []

    # Pass 2: dense around hot zones (hot pages themselves already judged in pass 1)
    dense_candidates: set[int] = set()
    for hp in hot_pages:
        for p in range(max(start, hp - window), min(end, hp + window) + 1):
            dense_candidates.add(p)
    dense_candidates -= set(coarse_pages)

    dense_pages = sorted(dense_candidates)
    console.print(f"  Pass 2 — dense ({len(dense_pages)} pages around "
                  f"{len(hot_pages)} hot zones)…")
    store.prewarm(dense_pages)
    pass2 = _run_pool(dense_pages, query, store, args, cache, workers)

    hits = [r for r in pass1 if r["verdict"] in ("YES", "PARTIAL")]
    for r in pass2:
        if r["verdict"] in ("YES", "PARTIAL"):
            icon = {"YES": "[green]✓[/]", "PARTIAL": "[yellow]~[/]"}[r["verdict"]]
            console.print(f"    p{r['page']}: {icon} {r['verdict']} — {r['reason'][:60]}")
            hits.append(r)

    hits.sort(key=lambda x: x["page"])
    return hits


def ramp_probe(args) -> None:
    """Measure gateway throughput vs concurrency before committing to a worker count.

    Runs 100 throwaway page-judgements at each concurrency level and prints
    calls/sec and error rate. Above the server's batch limit you get queueing or
    429/503 — a flat or falling calls/sec — so the knee is the worker count.
    """
    store = _get_page_store(args.pdf, args)
    probe_query = {"id": "ramp-probe", "query": "What is energy?"}
    n = 100
    lo, hi = max(args.page_start, 1), min(args.page_end, store.n_pages)
    span = list(range(lo, hi + 1))
    pages = [span[int(i * len(span) / n)] for i in range(n)] if span else []

    console.print(f"\n[bold]Ramp probe — {n} page-judgements per level[/]  "
                  f"judge: [cyan]{args.judge_backend}[/] / [cyan]{args.judge_model}[/]\n")
    table = Table(show_lines=True)
    table.add_column("Concurrency", justify="right")
    table.add_column("Elapsed (s)", justify="right")
    table.add_column("Calls/sec", justify="right")
    table.add_column("Errors", justify="right")
    table.add_column("Error rate", justify="right")

    for conc in (1, 4, 8, 16, 32):
        store.prewarm(pages)
        t0 = time.time()
        results = _run_pool(pages, probe_query, store, args, cache=None, workers=conc)
        elapsed = time.time() - t0
        errors = sum(1 for r in results if r["verdict"] == "ERROR")
        table.add_row(str(conc), f"{elapsed:.1f}", f"{n / elapsed:.2f}",
                      str(errors), f"{errors / n:.0%}")
        console.print(f"  concurrency {conc:>2}: {n / elapsed:6.2f} calls/sec, "
                      f"{errors}/{n} errors")

    console.print(table)
    console.print("\n[bold]Set --workers to the knee[/] — the level with the best "
                  "calls/sec that has not started erroring.\n")


def add_scan_args(p: argparse.ArgumentParser) -> None:
    """The scan/throughput knobs shared by every tool that calls ``scan_query()``.

    Single source so ``expand_gold_labels.py`` and ``generate_negatives.py`` cannot
    drift from this script's scan semantics.
    """
    p.add_argument("--scan-stride", type=int, default=15,
                   help="Coarse pass: check every Nth page (default 15)")
    p.add_argument("--scan-window", type=int, default=8,
                   help="Dense pass: pages ± this many around each hot zone (default 8)")
    p.add_argument("--page-start", type=int, default=30,
                   help="First page to scan (default 30, skips front matter)")
    p.add_argument("--page-end", type=int, default=968,
                   help="Last page to scan (default 968)")
    p.add_argument("--workers", type=int, default=_DEFAULT_WORKERS,
                   help=f"Concurrent judge calls (default {_DEFAULT_WORKERS}; "
                        "set from --ramp-probe)")
    p.add_argument("--render-dpi", type=int, default=_RENDER_DPI,
                   help=f"DPI for the page image sent to the judge (default {_RENDER_DPI})")
    p.add_argument("--cache-file", default=_DEFAULT_CACHE,
                   help=f"Verdict cache (JSONL). Default: {_DEFAULT_CACHE}")
    p.add_argument("--no-cache", action="store_true",
                   help="Ignore and do not write the verdict cache (throwaway runs)")


def add_judge_args(p: argparse.ArgumentParser) -> None:
    """Judge-connection knobs for tools that default the judge to .env.

    Empty defaults, so ``resolve_judge()`` fills them from .env (JUDGE_MODEL
    precedence) unless the caller overrides one explicitly.
    """
    p.add_argument("--judge-backend", choices=["anthropic", "openai"], default="")
    p.add_argument("--judge-api-base", default="")
    p.add_argument("--judge-api-key", default="")
    p.add_argument("--judge-model", default="",
                   help="Judge model. Default: .env JUDGE_MODEL, else the generator")
    p.add_argument("--judge-from-env", action="store_true",
                   help="Take the judge connection from .env (default when --judge-* "
                        "flags are left empty)")


def main():
    p = argparse.ArgumentParser(description="Validate or scan-calibrate eval_queries.json with a judge LLM")
    p.add_argument("--pdf", required=True, help="Path to the textbook PDF")
    p.add_argument("--query-file", default="data/eval_queries.json")
    p.add_argument("--output-dir", default="data/eval_results")
    p.add_argument("--judge-backend", choices=["anthropic", "openai"], default="anthropic")
    p.add_argument("--judge-api-key", default="")
    p.add_argument("--judge-api-base", default="https://api.anthropic.com/v1")
    p.add_argument("--judge-model", default="claude-haiku-4-5-20251001")
    p.add_argument("--judge-from-env", action="store_true",
                   help="Take the judge connection from .env (JUDGE_MODEL precedence) "
                        "instead of the --judge-* flags")
    p.add_argument("--query-ids", nargs="*", help="Only process these query IDs (default: all)")
    # Scan mode + the shared scan/throughput knobs (Task 4a)
    p.add_argument("--scan", action="store_true",
                   help="Scan mode: find correct pages from scratch instead of validating existing labels")
    add_scan_args(p)
    p.add_argument("--ramp-probe", action="store_true",
                   help="Measure gateway calls/sec vs concurrency, then exit")
    args = p.parse_args()

    pdf_path = args.pdf
    if not Path(pdf_path).exists():
        console.print(f"[red]PDF not found: {pdf_path}[/]")
        sys.exit(1)

    if args.no_cache:
        args.cache_file = ""
    resolve_judge(args)

    try:
        if args.ramp_probe:
            ramp_probe(args)
            return

        all_queries = json.loads(Path(args.query_file).read_text())
        all_queries = [q for q in all_queries if not q.get("id", "").startswith("_")]

        if args.scan:
            # Scan mode: include uncalibrated queries too (that's the point)
            queries = [q for q in all_queries if q.get("query_type") != "visual"]
        else:
            queries = [q for q in all_queries if q.get("calibrated") and q.get("relevant_pages")]

        if args.query_ids:
            queries = [q for q in queries if q["id"] in args.query_ids]

        mode = "SCAN" if args.scan else "VALIDATE"
        console.print(f"\n[bold]{mode} mode — {len(queries)} queries[/]")
        console.print(f"Judge: [cyan]{args.judge_backend}[/] / [cyan]{args.judge_model}[/]")
        if args.scan:
            console.print(f"Workers: [cyan]{args.workers}[/] · "
                          f"page image dpi: [cyan]{args.render_dpi}[/]\n")

        store = _get_page_store(pdf_path, args)
        cache = _get_verdict_cache(args)

        all_results = []
        for query in queries:
            console.print(f"\n[bold]{query['id']}[/] {query['query'][:70]}")
            if args.scan:
                hits = scan_query(query, pdf_path, args)
                suggested = sorted({h["page"] for h in hits if h["verdict"] == "YES"})
                suggested_partial = sorted({h["page"] for h in hits if h["verdict"] == "PARTIAL"})
                console.print(f"  → YES pages:     {suggested or 'none'}")
                console.print(f"  → PARTIAL pages: {suggested_partial or 'none'}")
                all_results.append({
                    "id": query["id"],
                    "query": query["query"],
                    "query_type": query.get("query_type"),
                    "current_pages": query.get("relevant_pages"),
                    "suggested_yes": suggested,
                    "suggested_partial": suggested_partial,
                    "page_verdicts": hits,
                })
            else:
                page_verdicts = validate_query(query, store, args)
                all_results.append({
                    "id": query["id"],
                    "query": query["query"],
                    "query_type": query.get("query_type"),
                    "labeled_pages": query["relevant_pages"],
                    "page_verdicts": page_verdicts,
                })

        if cache is not None:
            console.print(f"\nVerdict cache: [cyan]{cache.hits}[/] hits / "
                          f"[cyan]{cache.misses}[/] misses → {cache.path}")
    finally:
        close_shared_resources()

    # ── Scan mode output ──────────────────────────────────────────────────────
    if args.scan:
        table = Table(title="Scan Results — Suggested Pages", show_lines=True)
        table.add_column("ID", style="cyan")
        table.add_column("Query", max_width=40)
        table.add_column("Current", style="dim")
        table.add_column("YES pages", style="green")
        table.add_column("PARTIAL pages", style="yellow")

        for r in all_results:
            table.add_row(
                r["id"], r["query"][:40],
                str(r.get("current_pages") or "—"),
                str(r["suggested_yes"] or "—"),
                str(r["suggested_partial"] or "—"),
            )
        console.print(table)

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
        out_path = output_dir / f"calibration_scan_{ts}.md"

        def _md_table(headers, rows):
            sep = "| " + " | ".join("---" for _ in headers) + " |"
            lines = ["| " + " | ".join(str(c) for c in h) + " |" for h in [headers]]
            lines.append(sep)
            for row in rows:
                lines.append("| " + " | ".join(str(c) for c in row) + " |")
            return "\n".join(lines)

        scan_rows = [
            [r["id"], r["query"][:55],
             str(r.get("current_pages") or "—"),
             str(r["suggested_yes"] or "none"),
             str(r["suggested_partial"] or "none")]
            for r in all_results
        ]
        detail_rows = [
            [r["id"], pv["page"], pv["verdict"], pv["reason"][:80]]
            for r in all_results for pv in r["page_verdicts"]
        ]

        report = (
            f"# Calibration Scan\n\n"
            f"**{datetime.now(timezone.utc).isoformat(timespec='seconds')}**  \n"
            f"Judge: {args.judge_backend} / {args.judge_model}  \n"
            f"Scan: pages {args.page_start}–{args.page_end}, "
            f"stride={args.scan_stride}, window=±{args.scan_window}, "
            f"workers={args.workers}, page image dpi={args.render_dpi}\n\n"
            f"## Suggested Labels\n\n"
            + _md_table(["ID", "Query", "Current pages", "Suggested YES", "Suggested PARTIAL"], scan_rows)
            + "\n\n## Per-Page Verdicts\n\n"
            + _md_table(["ID", "Page", "Verdict", "Reason"], detail_rows)
            + "\n"
        )
        out_path.write_text(report)
        console.print(f"\n[green]Scan report:[/] {out_path}")
        return

    # ── Validate mode output ──────────────────────────────────────────────────
    table = Table(title="Calibration Validation", show_lines=True)
    table.add_column("ID", style="cyan")
    table.add_column("Query", max_width=45)
    table.add_column("Pages", justify="center")
    table.add_column("✓ YES", justify="center", style="green")
    table.add_column("~ PARTIAL", justify="center", style="yellow")
    table.add_column("✗ NO", justify="center", style="red")
    table.add_column("Verdict")

    issues = []
    for r in all_results:
        verdicts = [v["verdict"] for v in r["page_verdicts"]]
        n_yes     = verdicts.count("YES")
        n_partial = verdicts.count("PARTIAL")
        n_no      = verdicts.count("NO")
        n_error   = verdicts.count("ERROR")
        n_pages   = len(verdicts)

        if n_error == n_pages:
            overall = "[red]ALL ERRORS[/]"
            issues.append(r)
        elif n_error > 0:
            overall = f"[red]{n_error} ERRORS[/]"
            issues.append(r)
        elif n_no == n_pages:
            overall = "[red]ALL WRONG[/]"
            issues.append(r)
        elif n_no > 0:
            overall = "[yellow]MIXED[/]"
            issues.append(r)
        elif n_partial == n_pages:
            overall = "[yellow]ALL PARTIAL[/]"
        else:
            overall = "[green]OK[/]"

        table.add_row(
            r["id"], r["query"][:45],
            str(n_pages), str(n_yes), str(n_partial), str(n_no),
            overall,
        )

    console.print(table)

    # Write markdown report
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    out_path = output_dir / f"calibration_validation_{ts}.md"

    def _md_table(headers, rows):
        sep = "| " + " | ".join("---" for _ in headers) + " |"
        lines = ["| " + " | ".join(headers) + " |", sep]
        for row in rows:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        return "\n".join(lines)

    summary_rows = []
    for r in all_results:
        verdicts = [v["verdict"] for v in r["page_verdicts"]]
        summary_rows.append([
            r["id"],
            r["query"][:55] + ("…" if len(r["query"]) > 55 else ""),
            ", ".join(str(p) for p in r["labeled_pages"]),
            verdicts.count("YES"), verdicts.count("PARTIAL"),
            verdicts.count("NO"), verdicts.count("ERROR"),
        ])

    detail_rows = []
    for r in all_results:
        for pv in r["page_verdicts"]:
            detail_rows.append([
                r["id"], pv["page"], pv["verdict"],
                pv["reason"][:80] + ("…" if len(pv["reason"]) > 80 else ""),
            ])

    report = (
        f"# Calibration Validation\n\n"
        f"**{datetime.now(timezone.utc).isoformat(timespec='seconds')}**  \n"
        f"Judge: {args.judge_backend} / {args.judge_model}\n\n"
        f"## Summary\n\n"
        + _md_table(["ID", "Query", "Labeled pages", "YES", "PARTIAL", "NO", "ERROR"], summary_rows)
        + "\n\n## Per-Page Verdicts\n\n"
        + _md_table(["ID", "Page", "Verdict", "Reason"], detail_rows)
        + "\n\n## Queries Needing Attention\n\n"
        + (
            "\n".join(
                f"- **{r['id']}** — labeled {r['labeled_pages']}: "
                + "; ".join(
                    f"p{v['page']}={v['verdict']}" for v in r["page_verdicts"]
                )
                for r in issues
            ) or "None — all labels validated."
        )
        + "\n"
    )

    out_path.write_text(report)
    console.print(f"\n[green]Validation report:[/] {out_path}")

    if issues:
        console.print(f"\n[yellow]{len(issues)} queries have label issues — review the report.[/]")
    else:
        console.print("\n[green]All labels validated by judge LLM.[/]")


if __name__ == "__main__":
    main()
