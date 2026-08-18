#!/usr/bin/env python3
"""
Intent classifier training pipeline.

Steps
-----
1. Generate synthetic queries per intent using the configured LLM (Llama 3.2).
2. Validate each (query, intent) pair using a different-family judge LLM
   (Claude / GPT-4 / any OpenAI-compatible) to avoid same-model confirmation bias.
3. Embed validated queries with Jina v3 (same model used at runtime).
4. Train Logistic Regression on the embeddings.
5. Evaluate on 20% held-out split — per-class F1 + confusion matrix.
6. Save model to data/models/intent_classifier.pkl.

Usage
-----
# Full pipeline (generate + validate + train)
uv run python scripts/train_intent_classifier.py \\
    --judge-backend openai \\
    --judge-api-base https://api.anthropic.com/v1 \\
    --judge-api-key sk-ant-... \\
    --judge-model claude-3-haiku-20240307

# Skip validation (use all generated queries as-is)
uv run python scripts/train_intent_classifier.py --judge-backend skip

# Re-train from an existing dataset (skip generation + validation)
uv run python scripts/train_intent_classifier.py --train-only

# Generate only (inspect before validating)
uv run python scripts/train_intent_classifier.py --generate-only
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

console = Console()

# ── Intent definitions ────────────────────────────────────────────────────

INTENTS = ["factual", "overview", "multihop", "visual"]

# Generation prompts — one per intent, designed for physics education
GENERATION_PROMPTS = {
    "factual": """\
Generate {n} diverse, realistic questions that a physics student would ask \
when looking up a specific fact, definition, value, or formula.
Each question should:
- Have a single, specific answer (a definition, a value, a law statement, a formula)
- Cover varied topics: mechanics, thermodynamics, electromagnetism, quantum, waves, optics
- Vary in phrasing: some start with "What is", "Define", "State", "What does X equal", etc.
- Be realistic — a real student would actually ask this

Return ONLY a JSON array of strings, no other text:
["question 1", "question 2", ...]""",

    "overview": """\
Generate {n} diverse questions that a physics student would ask when they want \
a broad summary, overview, or synthesis of a topic or chapter.
Each question should:
- Require summarizing multiple concepts or an entire topic area
- Use phrases like "overview", "summarize", "explain the main ideas", "key themes", \
"big picture", "how does X connect to Y", "what are the main concepts in"
- Cover varied topics: classical mechanics, thermodynamics, electromagnetism, quantum
- Be realistic — a real student wanting to understand the big picture

Return ONLY a JSON array of strings, no other text:
["question 1", "question 2", ...]""",

    "multihop": """\
Generate {n} diverse questions that a physics student would ask when they need \
to connect multiple concepts, understand prerequisites, or trace causal chains.
Each question should:
- Require connecting 2 or more concepts to answer (multi-hop reasoning)
- Ask about: prerequisites ("what do I need to know before X"), \
causal relationships ("why does X happen"), connections ("how does X relate to Y"), \
concept dependencies ("what is the relationship between X and Y")
- Cover varied topics across classical and modern physics
- Be realistic — a real student trying to build deep understanding

Return ONLY a JSON array of strings, no other text:
["question 1", "question 2", ...]""",

    "visual": """\
Generate {n} diverse questions that a physics student would ask when looking \
for a specific diagram, figure, graph, table, or illustration in a textbook.
Each question should:
- Ask to find or show a specific visual element
- Use phrases like: "show me", "find the diagram", "which page has the figure", \
"find the graph", "show the illustration", "find the table comparing", \
"which page shows the circuit diagram", "find the picture of"
- Reference specific physics content: force diagrams, wave graphs, circuit diagrams, \
phase diagrams, experimental setups, sinusoidal waves, energy level diagrams
- Be realistic — a real student trying to find a visual in their textbook

Return ONLY a JSON array of strings, no other text:
["question 1", "question 2", ...]""",
}

# Judge validation prompt
JUDGE_PROMPT = """\
You are evaluating whether a physics student query correctly matches an intent label.

Intent definitions:
- factual: asks for a single specific fact, definition, formula, or value. \
  Short, direct answer expected.
- overview: asks for a broad summary, overview, or synthesis of an entire topic or chapter.
- multihop: requires connecting multiple concepts, understanding prerequisites, \
  or tracing causal/relational chains.
- visual: asks to find a specific diagram, figure, graph, table, or illustration \
  in a textbook.

Query: "{query}"
Assigned intent: "{intent}"

Does this query correctly and unambiguously match the assigned intent?
Answer with YES or NO on the first line, then one sentence explaining why.
Only say YES if you are confident — when in doubt say NO."""


# ── LLM helpers ───────────────────────────────────────────────────────────

def call_generator(prompt: str, cfg) -> str:
    """Call the configured LLM (Llama 3.2) to generate queries."""
    from src.core.llm import call_llm
    return call_llm(
        prompt=prompt,
        system="You are a helpful assistant. Follow instructions exactly.",
        settings=cfg,
        json_mode=False,
    )


def call_judge(query: str, intent: str, args) -> bool:
    """Call the judge LLM (different family) to validate a query/intent pair."""
    if args.judge_backend == "skip":
        return True

    prompt = JUDGE_PROMPT.format(query=query, intent=intent)

    if args.judge_backend == "ollama":
        import httpx
        payload = {
            "model": args.judge_model,
            "prompt": prompt,
            "stream": False,
        }
        resp = httpx.post(
            f"{args.judge_api_base}/api/generate",
            json=payload,
            timeout=60,
        )
        resp.raise_for_status()
        answer = resp.json().get("response", "").strip()
    elif args.judge_backend == "anthropic":
        import httpx
        headers = {
            "x-api-key": args.judge_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = {
            "model": args.judge_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 100,
        }
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        answer = resp.json()["content"][0]["text"].strip()
    else:
        # OpenAI-compatible (GPT-4, local OpenAI-compat endpoints, etc.)
        import httpx
        headers = {
            "Authorization": f"Bearer {args.judge_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": args.judge_model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 100,
            "temperature": 0,
        }
        resp = httpx.post(
            f"{args.judge_api_base}/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip()

    return answer.upper().startswith("YES")


# ── Pipeline steps ────────────────────────────────────────────────────────

def step_generate(args, cfg, output_dir: Path) -> list[dict]:
    """Step 1: Generate synthetic queries for each intent."""
    dataset_path = output_dir / "synthetic_queries.json"

    # Resume from existing file if present
    if dataset_path.exists() and not args.force:
        existing = json.loads(dataset_path.read_text())
        console.print(f"[yellow]Loaded {len(existing)} existing queries from {dataset_path}[/]")
        return existing

    dataset: list[dict] = []
    n = args.queries_per_intent

    console.print(f"\n[bold]Step 1: Generating {n} queries per intent ({len(INTENTS)} intents)...[/]")

    for intent in INTENTS:
        console.print(f"  Generating [cyan]{intent}[/] queries...")
        prompt = GENERATION_PROMPTS[intent].format(n=n)

        try:
            raw = call_generator(prompt, cfg)
            # Parse JSON array from response
            raw = raw.strip()
            # Find the JSON array in the response
            start = raw.find("[")
            end   = raw.rfind("]") + 1
            if start == -1 or end == 0:
                raise ValueError("No JSON array found in response")
            queries = json.loads(raw[start:end])
            if not isinstance(queries, list):
                raise ValueError("Response is not a list")
            queries = [str(q).strip() for q in queries if str(q).strip()]
            console.print(f"    Generated [green]{len(queries)}[/] queries")
            for q in queries:
                dataset.append({
                    "query":     q,
                    "intent":    intent,
                    "validated": False,
                    "judge_yes": None,
                })
        except Exception as exc:
            console.print(f"    [red]Failed for {intent}: {exc}[/]")

    dataset_path.write_text(json.dumps(dataset, indent=2))
    console.print(f"  Saved {len(dataset)} queries to {dataset_path}")
    return dataset


def step_validate(dataset: list[dict], args, output_dir: Path) -> list[dict]:
    """Step 2: Validate each query with the judge LLM."""
    dataset_path = output_dir / "synthetic_queries.json"

    if args.judge_backend == "skip":
        console.print("\n[yellow]Step 2: Validation skipped (--judge-backend skip)[/]")
        for item in dataset:
            item["validated"] = True
            item["judge_yes"] = True
        dataset_path.write_text(json.dumps(dataset, indent=2))
        return dataset

    pending = [i for i, item in enumerate(dataset) if not item["validated"]]
    if not pending:
        console.print("\n[yellow]Step 2: All queries already validated[/]")
        return dataset

    console.print(f"\n[bold]Step 2: Validating {len(pending)} queries with {args.judge_model}...[/]")
    console.print("[dim]  (Cross-family validation: different LLM judges the generator output)[/]")

    yes_count = 0
    fail_count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Validating...", total=len(pending))

        for idx in pending:
            item = dataset[idx]
            try:
                result = call_judge(item["query"], item["intent"], args)
                item["validated"] = True
                item["judge_yes"] = result
                if result:
                    yes_count += 1
                else:
                    fail_count += 1
                # Save progress periodically
                if (yes_count + fail_count) % 20 == 0:
                    dataset_path.write_text(json.dumps(dataset, indent=2))
                time.sleep(0.1)  # rate limit
            except Exception as exc:
                logger.warning("Judge call failed for query '{}': {}", item["query"][:50], exc)
                fail_count += 1
            progress.advance(task)

    dataset_path.write_text(json.dumps(dataset, indent=2))

    total = yes_count + fail_count
    agreement = yes_count / total * 100 if total > 0 else 0
    console.print(f"  Judge agreed: [green]{yes_count}[/] YES, [red]{fail_count}[/] NO "
                  f"({agreement:.1f}% acceptance rate)")
    return dataset


def step_train(dataset: list[dict], args, output_dir: Path) -> None:
    """Steps 3-5: Embed, train, evaluate, save."""
    import numpy as np
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report, confusion_matrix
    import joblib

    from src.core.config import get_settings
    from src.pdf_ingestion.embedder import get_embedder

    # Filter to validated + judge-approved
    approved = [item for item in dataset if item.get("judge_yes") is True]
    if not approved:
        console.print("[red]No validated queries — nothing to train on.[/]")
        sys.exit(1)

    # Per-intent counts
    by_intent: dict[str, list[str]] = {i: [] for i in INTENTS}
    for item in approved:
        intent = item["intent"]
        if intent in by_intent:
            by_intent[intent].append(item["query"])

    console.print(f"\n[bold]Step 3: Embedding {len(approved)} validated queries...[/]")
    for intent, queries in by_intent.items():
        console.print(f"  {intent}: [cyan]{len(queries)}[/] queries")

    cfg      = get_settings()
    embedder = get_embedder(cfg)

    texts  = [item["query"]  for item in approved]
    labels = [item["intent"] for item in approved]

    with Progress(SpinnerColumn(), TextColumn("{task.description}"),
                  BarColumn(), TaskProgressColumn(), console=console) as progress:
        task = progress.add_task("Embedding...", total=len(texts))
        X = []
        for text in texts:
            X.append(embedder.embed_query(text))
            progress.advance(task)

    X = np.array(X, dtype=np.float32)
    y = np.array(labels)

    console.print(f"  Embeddings shape: {X.shape}")

    # Train / test split
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )
    console.print(f"\n[bold]Step 4: Training Logistic Regression "
                  f"({len(X_train)} train, {len(X_test)} test)...[/]")

    clf = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
    clf.fit(X_train, y_train)

    # Evaluate
    console.print("\n[bold]Step 5: Evaluation[/]")
    y_pred = clf.predict(X_test)
    report = classification_report(y_test, y_pred, output_dict=True)
    report_str = classification_report(y_test, y_pred)
    console.print(report_str)

    # Confusion matrix
    cm = confusion_matrix(y_test, y_pred, labels=INTENTS)
    cm_table = Table(title="Confusion Matrix", show_header=True)
    cm_table.add_column("Actual \\ Predicted", style="bold")
    for label in INTENTS:
        cm_table.add_column(label)
    for i, actual in enumerate(INTENTS):
        cm_table.add_row(actual, *[str(cm[i][j]) for j in range(len(INTENTS))])
    console.print(cm_table)

    overall_acc = report.get("accuracy", 0)
    console.print(f"\nOverall accuracy: [{'green' if overall_acc >= 0.85 else 'red'}]"
                  f"{overall_acc*100:.1f}%[/]")

    if overall_acc < 0.85:
        console.print("[yellow]  Accuracy below 0.85 — consider MLP or more training data.[/]")

    # Save model
    model_dir = Path(cfg.intent_classifier_path).parent
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = Path(cfg.intent_classifier_path)
    joblib.dump(clf, model_path)
    console.print(f"\n[green]Model saved to: {model_path}[/]")

    # Save metrics
    metrics_path = output_dir / "training_report.json"
    metrics_path.write_text(json.dumps({
        "n_train":        len(X_train),
        "n_test":         len(X_test),
        "overall_accuracy": overall_acc,
        "per_intent":     {k: v for k, v in report.items() if k in INTENTS},
        "by_intent_counts": {k: len(v) for k, v in by_intent.items()},
    }, indent=2))
    console.print(f"Metrics saved to: {metrics_path}")
    console.print(
        "\n[bold green]Done![/] The intent router will automatically use the trained "
        "classifier on next app start — no code changes needed."
    )


# ── CLI ───────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="Train intent classifier for Synapse intent router")

    # Pipeline control
    p.add_argument("--generate-only", action="store_true",
                   help="Only generate queries, do not validate or train")
    p.add_argument("--validate-only", action="store_true",
                   help="Only validate existing dataset, do not generate or train")
    p.add_argument("--train-only", action="store_true",
                   help="Only train on existing validated dataset")
    p.add_argument("--force", action="store_true",
                   help="Re-generate even if dataset file exists")

    # Generation
    p.add_argument("--queries-per-intent", type=int, default=250,
                   help="Number of queries to generate per intent (default: 250)")

    # Judge LLM (different family from generator)
    p.add_argument("--judge-backend", choices=["openai", "ollama", "anthropic", "skip"], default="skip",
                   help="Judge LLM backend. 'skip' uses all generated queries without validation.")
    p.add_argument("--judge-api-base", default="https://api.openai.com/v1",
                   help="Base URL for judge API (OpenAI-compatible or Ollama)")
    p.add_argument("--judge-api-key", default="",
                   help="API key for judge (required for openai backend)")
    p.add_argument("--judge-model", default="gpt-4o-mini",
                   help="Judge model name (e.g. gpt-4o-mini, claude-3-haiku-20240307)")

    # Output
    p.add_argument("--output-dir", default="data/intent_classifier",
                   help="Directory to save dataset and reports (default: data/intent_classifier)")

    return p.parse_args()


def main():
    args   = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    from src.core.config import get_settings
    cfg = get_settings()

    console.print("\n[bold blue]Synapse Intent Classifier Training Pipeline[/]")
    console.print(f"  Generator:  {cfg.llm_backend} / {cfg.ollama_model if cfg.llm_backend == 'ollama' else cfg.openai_model}")
    console.print(f"  Judge:      {args.judge_backend}" +
                  (f" / {args.judge_model}" if args.judge_backend != "skip" else " (disabled)"))
    console.print(f"  Output dir: {output_dir}\n")

    # Load existing dataset if available
    dataset_path = output_dir / "synthetic_queries.json"
    dataset: list[dict] = []
    if dataset_path.exists():
        dataset = json.loads(dataset_path.read_text())

    if args.train_only:
        if not dataset:
            console.print("[red]No dataset found. Run without --train-only first.[/]")
            sys.exit(1)
        step_train(dataset, args, output_dir)
        return

    if args.validate_only:
        if not dataset:
            console.print("[red]No dataset found. Run without --validate-only first.[/]")
            sys.exit(1)
        dataset = step_validate(dataset, args, output_dir)
        return

    # Full pipeline
    dataset = step_generate(args, cfg, output_dir)

    if args.generate_only:
        console.print("\n[yellow]Generation complete. Run without --generate-only to validate and train.[/]")
        return

    dataset = step_validate(dataset, args, output_dir)
    step_train(dataset, args, output_dir)


if __name__ == "__main__":
    main()
