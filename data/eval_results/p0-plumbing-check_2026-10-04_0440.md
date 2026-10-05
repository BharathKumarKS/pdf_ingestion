# p0-plumbing-check

**2026-10-04T04:40:45+00:00**

## Summary

| Scope | Recall@100 | MRR | Precision@20 | NDCG@20 | Faithfulness | Ans.Relevance | Citation Acc. | n / cal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Overall | 0.795 | 0.361 | 0.096 | 0.413 | — | — | — | 23/23 |
|   factual | 0.900 | 0.504 | 0.080 | 0.559 | — | — | — | 10/10 |
|   overview | 0.771 | 0.191 | 0.133 | 0.314 | — | — | — | 6/6 |
|   multihop | 0.665 | 0.302 | 0.086 | 0.288 | — | — | — | 7/7 |

## Per-Query Results

| ID | Query | Type | Recall@100 | MRR | P@20 | NDCG@20 | Retrieved pages | Labeled pages |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vec-001 | What is the formula for kinetic energy? | factual | 0.500 | 0.500 | 0.100 | 0.558 | 95, 228, 723 | 95, 252, 254, 270 |
| vec-002 | Define Newton's first law of motion | factual | 1.000 | 0.500 | 0.050 | 0.631 | 285, 176, 231 | 176 |
| vec-003 | What is the value of Planck's constant? | factual | 1.000 | 1.000 | 0.050 | 1.000 | 965, 332, 950 | 965 |
| vec-004 | What does Feynman say about the principle of least time… | factual | 1.000 | 0.143 | 0.050 | 0.356 | 467, 483, 456 | 459 |
| vec-005 | What is the difference between elastic and inelastic co… | factual | 1.000 | 1.000 | 0.100 | 1.000 | 208, 207, 316 | 207, 208 |
| vec-006 | What is Newton's second law of motion? | factual | 1.000 | 0.100 | 0.100 | 0.491 | 194, 231, 179 | 179, 181 |
| vec-007 | What is the formula for gravitational force? | factual | 1.000 | 0.250 | 0.100 | 0.398 | 278, 91, 264 | 182, 243 |
| vec-008 | Define momentum | factual | 1.000 | 1.000 | 0.050 | 0.613 | 178, 176, 332 | 178, 179 |
| vec-009 | What is the work-energy theorem? | factual | 0.500 | 0.043 | 0.050 | 0.150 | 893, 358, 262 | 254, 270 |
| vec-010 | What is the uncertainty principle? | factual | 1.000 | 0.500 | 0.150 | 0.393 | 135, 671, 689 | 668, 669, 672, 678 |
| raptor-001 | Give me an overview of how classical mechanics breaks d… | overview | 0.500 | 0.143 | 0.050 | 0.161 | 687, 349, 652 | 60, 693 |
| raptor-002 | Summarize the key themes in the chapter on conservation… | overview | 0.667 | 0.028 | 0.250 | 0.359 | 196, 250, 209 | 85, 97, 98, 198, 252, 273, 343, 344, … |
| raptor-003 | How does Feynman build up the concept of energy from me… | overview | 1.000 | 0.143 | 0.050 | 0.228 | 98, 70, 694 | 252 |
| raptor-004 | What are the main ideas connecting electricity and magn… | overview | 1.000 | 0.167 | 0.050 | 0.264 | 484, 286, 53 | 487, 492 |
| raptor-005 | How does the textbook introduce probability into physic… | overview | 0.462 | 0.333 | 0.250 | 0.468 | 120, 135, 691 | 120, 122, 124, 125, 126, 128, 133, 135, … |
| raptor-006 | How does Feynman explain the relationship between force… | overview | 1.000 | 0.333 | 0.150 | 0.406 | 264, 272, 273 | 273, 278, 280, 281 |
| graph-001 | Why does a satellite stay in orbit? | multihop | 0.333 | 0.200 | 0.050 | 0.296 | 141, 274, 492 | 142, 143, 274 |
| graph-002 | What should I understand before learning about Maxwell'… | multihop | 1.000 | 0.077 | 0.100 | 0.303 | 286, 537, 440 | 487, 488 |
| graph-003 | How is simple harmonic motion related to wave propagati… | multihop | 0.750 | 1.000 | 0.100 | 0.363 | 841, 836, 384 | 384, 385, 530, 870 |
| graph-004 | How do conservation laws appear across different areas … | multihop | 0.571 | 0.500 | 0.150 | 0.492 | 97, 209, 922 | 97, 213, 317, 331, 343, 344, 922 |
| graph-005 | What connects the inverse square law in gravity and ele… | multihop | 0.500 | 0.111 | 0.100 | 0.213 | 156, 55, 486 | 143, 144, 242, 243 |
| graph-006 | What concepts connect thermodynamics and statistical me… | multihop | 0.500 | 0.062 | 0.050 | 0.195 | 70, 765, 709 | 709, 728, 729, 780 |
| graph-007 | How does the concept of fields unify electricity, magne… | multihop | 1.000 | 0.167 | 0.050 | 0.153 | 53, 286, 156 | 487, 488 |

## Config

- **Tenant:** global
- **Collection:** knowledge_base
- **Embedder:** nomic-ai/nomic-embed-text-v1.5
- **SPLADE:** True
- **Reranker:** True (BAAI/bge-reranker-v2-m3)
- **Min content page:** 30
- **Score threshold:** 0.0
- **Judge:** none
- **Elapsed:** 136.2s
