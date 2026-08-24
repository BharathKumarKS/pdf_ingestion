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
  Outputs suggested relevant_pages for each query to update eval_queries.json.
  This is the ground-truth approach — no retriever bias.

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
        --page-start 30 --page-end 968

    # Scan only specific queries
    uv run python scripts/validate_eval_calibration.py ... --scan --query-ids vec-002 vec-007

Output: data/eval_results/calibration_validation_<ts>.md (validate)
        data/eval_results/calibration_scan_<ts>.md      (scan)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf as fitz  # PyMuPDF
import httpx
from loguru import logger
from rich.console import Console
from rich.table import Table

console = Console()

_JUDGE_PROMPT = """\
You are an expert physics educator validating whether a textbook page is \
relevant to a student's question.

Question: {query}

Page {page_number} content (truncated to 800 chars):
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


def extract_page_text(pdf_path: str, page_number: int) -> str:
    """Extract text from a 1-indexed PDF page using PyMuPDF."""
    try:
        doc = fitz.open(pdf_path)
        if page_number < 1 or page_number > len(doc):
            return f"[page {page_number} out of range — PDF has {len(doc)} pages]"
        page = doc[page_number - 1]  # PyMuPDF is 0-indexed
        text = page.get_text("text").strip()
        doc.close()
        return text[:800] if text else "[no text extracted]"
    except Exception as exc:
        return f"[extraction error: {exc}]"


def call_judge(prompt: str, args) -> str:
    """Call the judge LLM and return raw response text."""
    if args.judge_backend == "anthropic":
        headers = {
            "x-api-key": args.judge_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload = {
            "model": args.judge_model,
            "max_tokens": 120,
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()

    else:  # openai-compatible
        headers = {"Content-Type": "application/json"}
        if args.judge_api_key:
            headers["Authorization"] = f"Bearer {args.judge_api_key}"
        base = args.judge_api_base.rstrip("/")
        if base.endswith("/v1"):
            base = base[:-3]
        payload = {
            "model": args.judge_model,
            "max_tokens": 120,
            "messages": [
                {"role": "system", "content": "You are a physics expert validating textbook page relevance."},
                {"role": "user", "content": prompt},
            ],
        }
        resp = httpx.post(f"{base}/v1/chat/completions", headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()


def parse_verdict(response: str) -> tuple[str, str]:
    """Parse judge response into (verdict, reason). Strips <think> blocks."""
    import re
    # Strip chain-of-thought blocks (DeepSeek R1, Qwen3 thinking mode)
    cleaned = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL).strip()
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


def validate_query(query: dict, pdf_path: str, args) -> list[dict]:
    """Validate all labeled pages for one query. Returns list of page verdicts."""
    results = []
    for page_num in (query.get("relevant_pages") or []):
        text = extract_page_text(pdf_path, page_num)
        prompt = _JUDGE_PROMPT.format(
            query=query["query"],
            page_number=page_num,
            page_text=text,
        )
        try:
            raw = call_judge(prompt, args)
            verdict, reason = parse_verdict(raw)
        except Exception as exc:
            verdict, reason = "ERROR", str(exc)[:80]

        results.append({
            "page": page_num,
            "verdict": verdict,
            "reason": reason,
            "text_preview": text[:120].replace("\n", " "),
        })
        icon = {"YES": "✓", "PARTIAL": "~", "NO": "✗", "ERROR": "!"}.get(verdict, "?")
        console.print(f"    p{page_num}: [{icon}] {verdict} — {reason[:70]}")

    return results


def scan_query(query: dict, pdf_path: str, args) -> list[dict]:
    """
    Two-pass scan to find relevant pages for a query without any prior labels.
    Pass 1: coarse scan every scan_stride pages → find hot zones.
    Pass 2: dense scan all pages within scan_window of each hot zone.
    Returns list of {page, verdict, reason} for YES/PARTIAL hits.
    """
    import pymupdf as fitz
    doc = fitz.open(pdf_path)
    n_pages = len(doc)
    doc.close()

    start  = max(args.page_start, 1)
    end    = min(args.page_end, n_pages)
    stride = args.scan_stride
    window = args.scan_window

    def _judge_page(page_num: int) -> dict:
        text = extract_page_text(pdf_path, page_num)
        prompt = _JUDGE_PROMPT.format(
            query=query["query"], page_number=page_num, page_text=text,
        )
        try:
            raw = call_judge(prompt, args)
            verdict, reason = parse_verdict(raw)
        except Exception as exc:
            verdict, reason = "ERROR", str(exc)[:80]
        return {"page": page_num, "verdict": verdict, "reason": reason}

    # Pass 1: coarse
    console.print(f"  Pass 1 — coarse (every {stride} pages, {start}-{end})…")
    hot_pages: set[int] = set()
    coarse_pages = list(range(start, end + 1, stride))
    for page_num in coarse_pages:
        r = _judge_page(page_num)
        icon = {"YES": "[green]✓[/]", "PARTIAL": "[yellow]~[/]"}.get(r["verdict"], "[dim]·[/]")
        if r["verdict"] in ("YES", "PARTIAL"):
            console.print(f"    p{page_num}: {icon} {r['verdict']} — {r['reason'][:60]}")
            hot_pages.add(page_num)

    if not hot_pages:
        console.print("  [yellow]No hot zones found in coarse pass.[/]")
        return []

    # Pass 2: dense around hot zones
    dense_candidates: set[int] = set()
    for hp in hot_pages:
        for p in range(max(start, hp - window), min(end, hp + window) + 1):
            dense_candidates.add(p)
    # Remove already checked
    dense_candidates -= set(coarse_pages)

    console.print(f"  Pass 2 — dense ({len(dense_candidates)} pages around {len(hot_pages)} hot zones)…")
    hits = []
    # Re-add coarse hits
    for hp in hot_pages:
        r = _judge_page(hp)
        if r["verdict"] in ("YES", "PARTIAL"):
            hits.append(r)

    for page_num in sorted(dense_candidates):
        r = _judge_page(page_num)
        if r["verdict"] in ("YES", "PARTIAL"):
            icon = {"YES": "[green]✓[/]", "PARTIAL": "[yellow]~[/]"}.get(r["verdict"], "")
            console.print(f"    p{page_num}: {icon} {r['verdict']} — {r['reason'][:60]}")
            hits.append(r)

    hits.sort(key=lambda x: x["page"])
    return hits


def main():
    p = argparse.ArgumentParser(description="Validate or scan-calibrate eval_queries.json with a judge LLM")
    p.add_argument("--pdf", required=True, help="Path to the textbook PDF")
    p.add_argument("--query-file", default="data/eval_queries.json")
    p.add_argument("--output-dir", default="data/eval_results")
    p.add_argument("--judge-backend", choices=["anthropic", "openai"], default="anthropic")
    p.add_argument("--judge-api-key", default="")
    p.add_argument("--judge-api-base", default="https://api.anthropic.com/v1")
    p.add_argument("--judge-model", default="claude-haiku-4-5-20251001")
    p.add_argument("--query-ids", nargs="*", help="Only process these query IDs (default: all)")
    # Scan mode
    p.add_argument("--scan", action="store_true",
                   help="Scan mode: find correct pages from scratch instead of validating existing labels")
    p.add_argument("--scan-stride", type=int, default=15,
                   help="Coarse pass: check every Nth page (default 15)")
    p.add_argument("--scan-window", type=int, default=8,
                   help="Dense pass: pages ± this many around each hot zone (default 8)")
    p.add_argument("--page-start", type=int, default=30,
                   help="First page to scan (default 30, skips front matter)")
    p.add_argument("--page-end", type=int, default=968,
                   help="Last page to scan (default 968)")
    args = p.parse_args()

    pdf_path = args.pdf
    if not Path(pdf_path).exists():
        console.print(f"[red]PDF not found: {pdf_path}[/]")
        sys.exit(1)

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
    console.print(f"Judge: [cyan]{args.judge_backend}[/] / [cyan]{args.judge_model}[/]\n")

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
            page_verdicts = validate_query(query, pdf_path, args)
            all_results.append({
                "id": query["id"],
                "query": query["query"],
                "query_type": query.get("query_type"),
                "labeled_pages": query["relevant_pages"],
                "page_verdicts": page_verdicts,
            })

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
            f"stride={args.scan_stride}, window=±{args.scan_window}\n\n"
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
