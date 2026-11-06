# SESSION HANDOFF — 2026-11-02 (visual lane + generator metrics)

> ⚠️ **SUPERSEDED (2026-11-02, session 32).** This file was written mid-flight and both jobs it lists
> under "RUNNING NOW" have since **finished** — read **`HANDOFF.md` session 32 item 4** and
> `IMPROVEMENTS.md` **§I108** (the generator eval) / **§I109** (T3, flagged — its G8 anchor failed and
> was diagnosed as a **stale anchor**). Kept for the §3 exact command and the §6 environment block,
> which are still accurate.

> Written so a NEW session can pick up. Both background jobs were launched with
> `persist_on_release=true`, so they survive `/new`. Their **artifacts** (not their process ids) are
> the interface: read the files, not `process_manage`.

---

## 1. RUNNING NOW

| job | command | artifact / log | ETA |
|---|---|---|---|
| **Phase-3 VISUAL write** (ColPali for doc `7ba61432`) | `bash logs/p1/step10/run_phase3_visual.sh` | `logs/p1/step10/phase3_visual_result.json` + `phase3_visual_write_run_2026-11-02.txt` | ~35 min |
| **Full JUDGED run** (generator metrics, 133 queries) | see §3 | `data/eval_results/v3_judged_full_*.md` + `logs/p1/step10/v3_judged_full_run.txt` | ~1–1.5 h |

Both are **resumable / re-runnable** — if either died, just re-run its command.
The ColPali write is **checkpointed per batch** (`logs/p1/step10/phase3_visual_checkpoint.json`): a re-run
resumes, it does not restart. (It already crashed once on a Qdrant timeout at batch ~87 and resumed
cleanly after a retry was added.)

## 2. HOW TO CHECK (in the new session)

```bash
cd /Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion

# ColPali progress (current doc)
tail -3 logs/p1/step10/phase3_visual_write_run_2026-11-02.txt
curl -s -X POST http://10.0.10.65:6333/collections/visual_knowledge_base/points/count \
  -H 'Content-Type: application/json' \
  -d '{"exact":true,"filter":{"must":[{"key":"document_id","match":{"value":"7ba61432-c5e0-416d-aecf-25a232523481"}}]}}'
# expect ~968 when done (was 0 before this session; the OLD doc 6d55c52b has 1,033)

# Judged run progress
tail -20 logs/p1/step10/v3_judged_full_run.txt
ls -la data/eval_results/ | grep v3_judged
```

## 3. THE JUDGED RUN — exact command (re-run if needed)

```bash
unset PYTHONPATH
export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3
export DENSE_MODEL="nomic-ai/nomic-embed-text-v1.5" DENSE_DIM=768 DENSE_DIM_LOW=64
export DOCUMENT_PREFIX="search_document: " QUERY_INSTRUCTION="search_query: " DA_ENABLED=true

.venv/bin/python scripts/evaluate_rag.py \
  --query-file data/eval_queries_v2.json --skip-visual \
  --judge-backend openai --judge-api-base http://10.0.10.70:8000/v1 \
  --judge-api-key dummy --judge-model Qwen/Qwen3-VL-8B-Instruct \
  --run-name v3_judged_full --output-dir data/eval_results
```

⚠️ **The judge MUST be cross-family.** The generator is `openai/gpt-oss-20b`; the judge is
`Qwen/Qwen3-VL-8B-Instruct`. `config.yaml`'s default `judge_model` is gpt-oss-20b (same family) — do NOT
use it; the code warns a same-family judge is "indistinguishable from a genuinely faithful answer".

## 4. PENDING WORK (in order)

1. **When the ColPali write finishes** → run the visual-lane validation:
   `python logs/p1/step10/visual_lane_validation.py`
   (three-way split: in-book pages, in-domain concept images, near-domain, far-domain + an aperture sweep.
   Concept images are **SYNTHETIC matplotlib figures**; the in-domain gold is a **TEXT-lane proxy** — both
   are stated in the artifact's `provenance` block.)
2. **When the judged run finishes** → read the per-type faithfulness / answer_relevance table
   (`data/eval_results/v3_judged_full_*.md`). This CLOSES the "generator unmeasured" gap.
3. **Register the findings** in `IMPROVEMENTS.md` (visual lane write + validation; generator metrics).

## 5. WHAT IS STILL UNCOMMITTED (nothing has been committed this session)

  IMPROVEMENTS.md §I105, §I106 · the 3 pre-registrations under `.hermes/plans/` ·
  `wide_ce_endpoint.py` + `run_wide_ce.sh` · `wide_pool_k_sweep.py` · `wide_ce_k_sweep.py` (+ both
  verifiers + mutation proofs) · `per_type_k_sweep.py` (+ verifier + mutation) ·
  `phase3_visual_write.py` + `run_phase3_visual.sh` · `gen_concept_images.py` ·
  `visual_lane_validation.py` · `demo_deck.md` · `demo_runbook.md` · the app-parts probe · this file.

⚠️ The branch is far ahead of origin and **nothing is pushed**; sessions 13–27 were already uncommitted.

## 6. ENVIRONMENT (copy-paste)

```bash
cd /Users/bharathkumar/repo/Support_Vectors/Beyond_RAG_Advanced_Agentic_Knowledge_Architectures/Project/Team_Project/pdf_ingestion
unset PYTHONPATH
export QDRANT_HOST=10.0.10.65 QDRANT_COLLECTION=knowledge_base_v3
export DENSE_MODEL="nomic-ai/nomic-embed-text-v1.5" DENSE_DIM=768 DENSE_DIM_LOW=64
export DOCUMENT_PREFIX="search_document: " QUERY_INSTRUCTION="search_query: " DA_ENABLED=true
```

  Qdrant `10.0.10.65:6333` · LLM router `10.0.10.70:8000` (gpt-oss-20b, Qwen3-VL-8B, DeepSeek-R1-7B) ·
  embeddings/rerank `10.0.10.70:8123` · Memgraph `localhost:7687` (user `memgraph`) · app on **8503**
  (`.venv/bin/streamlit` — NOT `uv run streamlit`; 8501/8502 belong to the other repo).
