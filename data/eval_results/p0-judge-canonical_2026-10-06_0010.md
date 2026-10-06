# p0-judge-canonical

**2026-10-06T00:10:11+00:00**

## Summary

| Scope | Recall@100 | Recall@20 | Hit@20 | MRR | NDCG@20 | Faithfulness | Ans.Relevance | Citation Acc. | n / cal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Overall | 0.795 | 0.636 | 1.000 | 0.361 | 0.432 | 0.701 | 0.927 | 1.000 | 23/23 |
|   factual | 0.900 | 0.775 | 1.000 | 0.504 | 0.573 | 0.752 | 0.867 | 1.000 | 10/10 |
|   overview | 0.771 | 0.560 | 1.000 | 0.192 | 0.366 | 0.645 | 1.000 | 1.000 | 6/6 |
|   multihop | 0.665 | 0.502 | 1.000 | 0.302 | 0.288 | 0.676 | 0.952 | 1.000 | 7/7 |

## Run integrity

- **Synthesis succeeded:** 23/30
- **Faithfulness computed:** 23/30
- **Judge calls:** 1040 (0 failed)

## Per-Query Results

| ID | Query | Type | Recall@100 | Recall@20 | Hit@20 | MRR | NDCG@20 | Retrieved pages | Labeled pages |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vec-001 | What is the formula for kinetic energy? | factual | 0.500 | 0.500 | 1.000 | 0.500 | 0.264 | 272, 386, 301 | 95, 252, 254, 270 |
| vec-002 | Define Newton's first law of motion | factual | 1.000 | 1.000 | 1.000 | 0.500 | 0.500 | 231, 488, 176 | 176 |
| vec-003 | What is the value of Planck's constant? | factual | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 965, 332, 677 | 965 |
| vec-004 | What does Feynman say about the principle of least time… | factual | 1.000 | 1.000 | 1.000 | 0.143 | 0.631 | 462, 459, 482 | 459 |
| vec-005 | What is the difference between elastic and inelastic co… | factual | 1.000 | 1.000 | 1.000 | 1.000 | 0.544 | 201, 277, 208 | 207, 208 |
| vec-006 | What is Newton's second law of motion? | factual | 1.000 | 1.000 | 1.000 | 0.100 | 0.624 | 197, 179, 178 | 179, 181 |
| vec-007 | What is the formula for gravitational force? | factual | 1.000 | 0.500 | 1.000 | 0.250 | 0.613 | 243, 138, 264 | 182, 243 |
| vec-008 | Define momentum | factual | 1.000 | 0.500 | 1.000 | 1.000 | 0.613 | 178, 312, 201 | 178, 179 |
| vec-009 | What is the work-energy theorem? | factual | 0.500 | 0.500 | 1.000 | 0.043 | 0.387 | 272, 270, 339 | 254, 270 |
| vec-010 | What is the uncertainty principle? | factual | 1.000 | 0.750 | 1.000 | 0.500 | 0.554 | 671, 678, 672 | 668, 669, 672, 678 |
| raptor-001 | Give me an overview of how classical mechanics breaks d… | overview | 0.500 | 0.500 | 1.000 | 0.143 | 0.150 | 59, 687, 668 | 60, 693 |
| raptor-002 | Summarize the key themes in the chapter on conservation… | overview | 0.667 | 0.556 | 1.000 | 0.031 | 0.380 | 805, 84, 344 | 85, 97, 98, 198, 252, 273, 343, 344, … |
| raptor-003 | How does Feynman build up the concept of energy from me… | overview | 1.000 | 1.000 | 1.000 | 0.143 | 1.000 | 252, 30, 277 | 252 |
| raptor-004 | What are the main ideas connecting electricity and magn… | overview | 1.000 | 0.500 | 1.000 | 0.167 | 0.157 | 243, 57, 440 | 487, 492 |
| raptor-005 | How does the textbook introduce probability into physic… | overview | 0.462 | 0.308 | 1.000 | 0.333 | 0.236 | 729, 691, 693 | 120, 122, 124, 125, 126, 128, 133, 135, … |
| raptor-006 | How does Feynman explain the relationship between force… | overview | 1.000 | 0.500 | 1.000 | 0.333 | 0.274 | 272, 260, 262 | 273, 278, 280, 281 |
| graph-001 | Why does a satellite stay in orbit? | multihop | 0.333 | 0.333 | 1.000 | 0.200 | 0.296 | 141, 274, 492 | 142, 143, 274 |
| graph-002 | What should I understand before learning about Maxwell'… | multihop | 1.000 | 1.000 | 1.000 | 0.077 | 0.303 | 286, 537, 440 | 487, 488 |
| graph-003 | How is simple harmonic motion related to wave propagati… | multihop | 0.750 | 0.500 | 1.000 | 1.000 | 0.363 | 841, 836, 384 | 384, 385, 530, 870 |
| graph-004 | How do conservation laws appear across different areas … | multihop | 0.571 | 0.429 | 1.000 | 0.500 | 0.492 | 97, 209, 922 | 97, 213, 317, 331, 343, 344, 922 |
| graph-005 | What connects the inverse square law in gravity and ele… | multihop | 0.500 | 0.500 | 1.000 | 0.111 | 0.213 | 156, 55, 486 | 143, 144, 242, 243 |
| graph-006 | What concepts connect thermodynamics and statistical me… | multihop | 0.500 | 0.250 | 1.000 | 0.062 | 0.195 | 70, 765, 709 | 709, 728, 729, 780 |
| graph-007 | How does the concept of fields unify electricity, magne… | multihop | 1.000 | 0.500 | 1.000 | 0.167 | 0.153 | 53, 286, 156 | 487, 488 |

## Config

- **Tenant:** global
- **Collection:** knowledge_base
- **Embedder:** nomic-ai/nomic-embed-text-v1.5
- **SPLADE:** True
- **Reranker:** True (BAAI/bge-reranker-v2-m3)
- **Min content page:** 30
- **Score threshold:** 0.0
- **Judge:** Qwen/Qwen3-VL-8B-Instruct
- **Elapsed:** 706.3s

<details>
<summary>Full config snapshot</summary>

```json
{
  "chunking": {
    "chunk_overlap": 64,
    "chunk_size": 512
  },
  "colbert": {
    "active": true,
    "enabled": true
  },
  "derivative_artifacts": {
    "card_types": [
      "summary",
      "definition",
      "example",
      "misconception",
      "question",
      "objective",
      "formula",
      "factoid"
    ],
    "collection": "derivative_artifacts",
    "enabled": true
  },
  "embedding": {
    "dim": 768,
    "model": "nomic-ai/nomic-embed-text-v1.5"
  },
  "intent_router": {
    "classifier_path": "data/models/intent_classifier.pkl",
    "enabled": true,
    "mode": "trained_classifier"
  },
  "llm_generator": {
    "backend": "openai",
    "model": "openai/gpt-oss-20b"
  },
  "mmr": {
    "candidates": 100,
    "enabled": true,
    "lambda": 0.7
  },
  "raptor": {
    "max_levels": 3,
    "min_cluster_size": 2
  },
  "reranker": {
    "enabled": true,
    "model": "BAAI/bge-reranker-v2-m3",
    "top_k": 20
  },
  "retriever": {
    "collection": "knowledge_base",
    "fetch_k": 100,
    "splade_enabled": true,
    "type": "hybrid (SPLADE+dense RRF)"
  },
  "score_threshold": 0.0,
  "tenant_id": "global"
}
```

</details>
