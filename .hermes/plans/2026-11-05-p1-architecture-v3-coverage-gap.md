# Architecture v3.0 — coverage & gap (2026-11-05)

> Reference: `Project/pdf_ingestion_Architecture.jpeg` — *"Synapse Learning Worlds — Hybrid RAG
> Architecture Specification v3.0"* (author Bharath, target Synapse Engine).
> Statuses are grounded in the live repo, not in the diagram's intent.
> Legend: **✅ built · 🟡 partial · ⬜ absent (promised, nothing in `src/`) · ⏸ deferred by an explicit decision.**

---

## 1. Offline ingestion & knowledge construction

| diagram component | status | evidence in repo | gap |
|---|---|---|---|
| Data source — Global baseline (Feynman) | ✅ | 3,796 chunks, doc `7ba61432`, `knowledge_base_v3`; SQLite `synapse.db` | — |
| Data source — Ephemeral upload (single-topic PDF) | 🟡 | `tenant_id` plumbed through `store.py`; `scripts/ingest_base_textbook.py` | no per-upload tenant lifecycle; NG-P5 (NiceGUI upload) pending |
| Doc processing — Docling engine v2 | ✅ | `parser.py` (Docling, `do_table_structure=True`) | — |
| Doc processing — Noise filter | 🟡 | `content_filter.py` + `MIN_CONTENT_PAGE`/`MAX_CONTENT_PAGE` window | page-window filter, not a content noise model |
| Metadata — text extraction | ✅ | Docling text + heading hierarchy | — |
| Metadata — chart / table | 🟡 | tables parsed into `PageContent.tables: list[str]` | tables not separately indexed, filtered, or retrievable |
| Metadata — image (optional) | ✅ | page rasterisation → `image_bytes` → ColPali | — |
| Metadata — ID mapping | ✅ | `chunk_id` / `qdrant_point_id` / `document_id` | — |
| Metadata — qwen2.5 Math / LaTeX extraction | ⬜ | no LaTeX/formula extractor in `src/` | — |
| Metadata — difficulty | 🟡 | `difficulty` column in `database.py` + payload (`store.py:308`) | never populated; no classifier; no filter |
| Metadata — URL / video timestamps | ⬜ | — | — |
| Metadata — embedding version | 🟡 | versioning is implicit via collection name (`knowledge_base_v2/v3`) | no explicit `embedding_version` field |
| Adaptive chunking — metadata-aware | 🟡 | `chunker.py` preserves headings | metadata does not shape chunk boundaries |
| Adaptive chunking — semantic (Chonkie) | ✅ | `chunker.py` | — |
| Adaptive chunking — late chunking | ✅ built, ⏸ off default path | `late_chunk_embedder.py`; **measured HARM** (§I87), superseded by pooled re-embed (§I89) | kept but not the shipped path |
| Embedding — text (BGE-base / BGE-large) | ⬜ superseded | built nomic-768 + Qwen3-1024 instead; BGE never used | diagram is stale on the model choice |
| Embedding — visual (ColPali VLM, 128-dim/page) | ✅ | `colpali_embedder.py`; `visual_knowledge_base` = 2,001 pts | — |
| Enrichment — cross-aspect linker (entities/concepts) | ✅ | `graph_builder.py` + `entity_resolution.py`; Memgraph 6,065 concepts / 47,209 edges | — |
| Enrichment — card generation (8 types) | ✅ | `card_generator.py` `CardType` ×8; 157,826 cards | — |
| Enrichment — concept clustering | ✅ | `community_summaries.py`, `graph_analytics.py` (Leiden) | — |
| Enrichment — question generation | ✅ | `CardType.QUESTION` | — |
| Enrichment — learning objectives | ✅ | `CardType.OBJECTIVE` | — |
| Enrichment — MARS / hypergraph indexing | ⬜ | no MARS/hypergraph code | — |
| Enrichment (visual) — object/feature index, image2text, diagram extraction, caption enrichment | ⬜ | ColPali yields page vectors only | no object index, no captioning, no diagram extraction |
| Persistence — Qdrant (text_dense, text_sparse, image) | ✅ | named vectors; ⚠️ sparse lane DOWN on cluster 2026-11-05 | — |
| Persistence — Memgraph graph DB | ✅ | — | — |
| Persistence — SQLite relational | ✅ | `data/synapse.db` | — |
| Persistence — key-value store (Redis-style cache) | ⬜ | file caches only (`embed_cache.py`, `hyde_cache.py`) | no Redis |

## 2. Online inference & intent-routed RAG

| diagram component | status | evidence | gap |
|---|---|---|---|
| User query | ✅ | — | — |
| Input guardrail — prompt injection | ⬜ | none | **Gate 1** (R8) |
| Input guardrail — off-topic filter | 🟡 | `intent_router.py` classifies factual/overview/multihop/visual | no `out_of_scope` class → needs retrain (§I114) |
| Conversation history — recent / summary / profile | ⬜ | none | — |
| Intent classifier & router | ✅ | `intent_router.py` (sklearn + `dense_dim` schema check) | ⚠️ eval BYPASSES it (§I116) — every published number is oracle-routed |
| Dynamic cache (Redis, TTL, doc-version key) | ⬜ | none | — |
| Metadata filtering (subject / grade / scope / difficulty) | ⬜ | fields exist in payload (`store.py:306-308`); no filter applied in `search` | — |
| Retrieval — vector (text / table) | ✅ | dense + sparse → RRF (`search_fused`) | sparse lane down |
| Retrieval — visual (ColPali) | ✅ | `run_visual_retrieval` | no labelled metric; aperture cannot separate (§I107) |
| Retrieval — web search | ⬜ | none | — |
| Retrieval — RAPTOR | ✅ built, ⏸ off eval path | `raptor_tree.py`, `search_raptor` | resolved HARM as a pool participant (§I98) |
| Retrieval — behavioral search | ⬜ | none | — |
| RRF fusion | ✅ | `search_fused` | — |
| Context manager & ranker — cross-encoder re-ranking | ✅ | `reranker.py` | net HARM at the endpoint (§I97) |
| Generation & response | ✅ | `evaluate_rag.synthesize` | — |
| Output guardrail — grounding (claim-level NLI) | 🟡 | LLM-judge faithfulness exists in the EVAL only | **Gate 2** (C1–C5); not in the product path |
| Output guardrail — answer leakage guard | ⬜ | none | Gate 2 |
| Output guardrail — unsafe content | ⬜ | none | Gate 2 |
| Response pipeline — prompt builder / generation / LLM synthesis L2/L3 / citation builder | ✅ | `synthesize`; citations emitted | citation FORMAT inconsistent (§I115) |
| Session cache (LRU) | ⬜ | none | — |
| Output safety & grounding band (groundedness, injection score, PII redaction, leakage, canary) | ⬜ | none | Act II / III |

## 3. Observability & telemetry (the diagram marks this "NEXT")

| component | status | evidence |
|---|---|---|
| Arize Phoenix observability | ✅ | `src/core/telemetry.py`; O1 manual `llm.call` spans |
| Retrieval quality (recall / MRR / nDCG) | ✅ | `scripts/evaluate_rag.py` harness + artifacts |
| Latency & throughput | ✅ | `src/core/query_trace.py` (O2) |
| Token usage & cost | 🟡 | span carries `prompt_chars`/`response_chars`; no $ accounting |
| Hallucination rate (grounding score) | 🟡 | eval-only faithfulness; not in the product path |
| User / learner outcomes (progress & engagement) | ⬜ | — |

## 4. Headline

The **retrieval core** the diagram draws (ingestion Phases 1–3, dense+sparse+visual+graph, RRF, CE,
RAPTOR, cards, Memgraph, Qdrant) is essentially **built and measured** — and measured hard: much of
the diagram's *retrieval* side has been shown to be at or near a null (§I97–§I113).

The **gap is concentrated in three bands the diagram draws but the repo has not built**:

1. **Both guardrail gates — the entire security + integrity surface.** Input side: sanitization,
   length, gibberish, language, domain/`out_of_scope`, toxicity, PII, injection. Output side:
   claim-level grounding, leakage, unsafe content, citation faithfulness. This is the whole of the
   course's Week 6 and it is **absent from `src/`**. → this plan.
2. **The stateful/online layer** — dynamic cache (Redis), session cache (LRU), conversation memory,
   metadata filtering, web/behavioral retrieval, rate limiting.
3. **The visual-enrichment and metadata-extraction depth** — MARS/hypergraph, object/caption/diagram
   extraction, LaTeX/difficulty/URL metadata; and the **ephemeral-upload lifecycle** (the diagram's
   title promises a second pipeline the repo has not built).

Band 1 is the owner's stated next task; bands 2–3 remain backlog (NG-P4→P6, VL-L1).
