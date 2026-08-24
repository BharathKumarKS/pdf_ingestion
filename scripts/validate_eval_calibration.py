#!/usr/bin/env python3
"""
Independent LLM validation of eval_queries.json calibration.

For each calibrated query, extracts text from its labeled pages and asks
a judge LLM (different family from the retriever's generation LLM) whether
each page is genuinely relevant to the query.

This catches circular calibration — labels that drifted toward the retriever's
biases rather than ground truth.

Usage:
    # Validate using Anthropic Claude (recommended — different family from Llama)
    uv run python scripts/validate_eval_calibration.py \\
        --pdf data/base_textbooks/feynman-lectures-on-physics-volume1.pdf \\
        --judge-backend anthropic \\
        --judge-api-key sk-ant-... \\
        --judge-model claude-haiku-4-5-20251001

    # Or validate using the OpenAI-compatible endpoint with a different model
    uv run python scripts/validate_eval_calibration.py \\
        --pdf data/base_textbooks/feynman-lectures-on-physics-volume1.pdf \\
        --judge-backend openai \\
        --judge-api-base http://10.0.10.51:8000 \\
        --judge-model some-other-model

Output: data/eval_results/calibration_validation_<ts>.md
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
    """Parse judge response into (verdict, reason)."""
    lines = [l.strip() for l in response.strip().splitlines() if l.strip()]
    verdict = "UNKNOWN"
    reason = response[:120]
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


def main():
    p = argparse.ArgumentParser(description="Validate eval_queries.json calibration with a judge LLM")
    p.add_argument("--pdf", required=True, help="Path to the textbook PDF")
    p.add_argument("--query-file", default="data/eval_queries.json")
    p.add_argument("--output-dir", default="data/eval_results")
    p.add_argument("--judge-backend", choices=["anthropic", "openai"], default="anthropic")
    p.add_argument("--judge-api-key", default="")
    p.add_argument("--judge-api-base", default="https://api.anthropic.com/v1")
    p.add_argument("--judge-model", default="claude-haiku-4-5-20251001")
    p.add_argument("--query-ids", nargs="*", help="Only validate these query IDs (default: all)")
    args = p.parse_args()

    pdf_path = args.pdf
    if not Path(pdf_path).exists():
        console.print(f"[red]PDF not found: {pdf_path}[/]")
        sys.exit(1)

    queries = json.loads(Path(args.query_file).read_text())
    queries = [q for q in queries if not q.get("id", "").startswith("_")]
    queries = [q for q in queries if q.get("calibrated") and q.get("relevant_pages")]
    if args.query_ids:
        queries = [q for q in queries if q["id"] in args.query_ids]

    console.print(f"\n[bold]Validating {len(queries)} calibrated queries[/]")
    console.print(f"Judge: [cyan]{args.judge_backend}[/] / [cyan]{args.judge_model}[/]\n")

    all_results = []
    for query in queries:
        console.print(f"[bold]{query['id']}[/] {query['query'][:70]}")
        page_verdicts = validate_query(query, pdf_path, args)
        all_results.append({
            "id": query["id"],
            "query": query["query"],
            "query_type": query.get("query_type"),
            "labeled_pages": query["relevant_pages"],
            "page_verdicts": page_verdicts,
        })

    # Summary table
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
        n_yes = verdicts.count("YES")
        n_partial = verdicts.count("PARTIAL")
        n_no = verdicts.count("NO")
        n_pages = len(verdicts)

        if n_no == n_pages:
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
            verdicts.count("YES"), verdicts.count("PARTIAL"), verdicts.count("NO"),
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
        + _md_table(["ID", "Query", "Labeled pages", "YES", "PARTIAL", "NO"], summary_rows)
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
