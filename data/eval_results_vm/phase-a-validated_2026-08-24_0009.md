# phase-a-validated

**2026-08-24T00:09:22+00:00**

## Summary

| Scope | Recall@20 | MRR | Precision@6 | NDCG@6 | Faithfulness | Ans.Relevance | Citation Acc. | n / cal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Overall | 0.212 | 0.491 | 0.355 | 0.399 | 0.000 | 0.000 | 1.000 | 23/23 |
|   factual | 0.221 | 0.396 | 0.267 | 0.354 | 0.000 | 0.000 | 1.000 | 10/10 |
|   overview | 0.245 | 0.583 | 0.500 | 0.499 | 0.000 | 0.000 | 1.000 | 6/6 |
|   multihop | 0.171 | 0.549 | 0.357 | 0.377 | 0.000 | 0.000 | 1.000 | 7/7 |

## Per-Query Results

| ID | Query | Type | Recall@20 | MRR | P@6 | NDCG@6 | Retrieved pages | Labeled pages |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vec-001 | What is the formula for kinetic energy? | factual | 1.000 | 1.000 | 0.667 | 1.402 | 95, 276, 252 | 95, 252 |
| vec-002 | Define Newton's first law of motion | factual | 0.000 | 0.500 | 0.167 | 0.246 | 141, 179, 181 | 177, 178, 179, 180 |
| vec-003 | What is the value of Planck's constant? | factual | 0.000 | 0.000 | 0.000 | 0.000 | 763, 965, 965 | 678, 679, 680, 681, 682, 683, 684, 685 |
| vec-004 | What does Feynman say about the principle of least acti… | factual | 0.000 | 0.125 | 0.000 | 0.000 | 8, 18, 466 | 452, 453, 454, 455, 456, 457, 458, 459, … |
| vec-005 | What is the difference between elastic and inelastic co… | factual | 0.400 | 1.000 | 0.667 | 0.775 | 208, 207, 207 | 200, 201, 202, 203, 204, 205, 206, 207, … |
| vec-006 | What is Newton's second law of motion? | factual | 0.444 | 0.500 | 0.500 | 0.472 | 199, 182, 179 | 177, 178, 179, 180, 181, 182, 183, 184, … |
| vec-007 | What is the formula for gravitational force? | factual | 0.000 | 0.000 | 0.000 | 0.000 | 243, 91, 276 | 143, 144, 145, 146, 147, 148 |
| vec-008 | Define momentum | factual | 0.250 | 0.500 | 0.167 | 0.246 | 340, 178, 312 | 177, 178, 179, 180 |
| vec-009 | What is the work-energy theorem? | factual | 0.000 | 0.000 | 0.000 | 0.000 | 262, 787, 272 | 240, 241, 242, 243, 244, 245, 246, 247, … |
| vec-010 | What is the uncertainty principle? | factual | 0.111 | 0.333 | 0.500 | 0.399 | 671, 672, 668 | 660, 661, 662, 663, 664, 665, 666, 667, … |
| raptor-001 | Give me an overview of how classical mechanics breaks d… | overview | 0.556 | 1.000 | 0.667 | 0.762 | 686, 693, 349 | 349, 686, 687, 688, 689, 690, 691, 692, … |
| raptor-002 | Summarize the key themes in the chapter on conservation… | overview | 0.143 | 0.500 | 0.667 | 0.590 | 84, 97, 98 | 97, 98, 195, 196, 197, 198, 199, 200, … |
| raptor-003 | How does Feynman build up the concept of energy from me… | overview | 0.000 | 0.000 | 0.000 | 0.000 | 18, 800, 786 | 240, 241, 242, 243, 244, 245, 246, 247, … |
| raptor-004 | What are the main ideas connecting electricity and magn… | overview | 0.273 | 0.500 | 0.333 | 0.321 | 484, 487, 286 | 485, 486, 487, 488, 489, 490, 491, 492, … |
| raptor-005 | How does the textbook introduce probability into physic… | overview | 0.000 | 0.500 | 0.333 | 0.321 | 693, 670, 18 | 119, 120, 121, 122, 123, 124, 125, 126, … |
| raptor-006 | How does Feynman explain the relationship between force… | overview | 0.500 | 1.000 | 1.000 | 1.000 | 274, 278, 281 | 274, 275, 276, 277, 278, 279, 280, 281, … |
| graph-001 | Why does a satellite stay in orbit? | multihop | 0.091 | 1.000 | 0.833 | 0.892 | 274, 148, 274 | 139, 140, 141, 142, 143, 144, 145, 146, … |
| graph-002 | What should I understand before learning about Maxwell'… | multihop | 0.000 | 0.200 | 0.167 | 0.117 | 286, 484, 691 | 485, 486, 487, 488, 489, 490, 491, 492, … |
| graph-003 | How is simple harmonic motion related to wave propagati… | multihop | 0.364 | 0.333 | 0.167 | 0.151 | 841, 859, 384 | 382, 383, 384, 385, 386, 870, 871, 872, … |
| graph-004 | How do conservation laws appear across different areas … | multihop | 0.273 | 1.000 | 0.667 | 0.775 | 97, 922, 97 | 52, 53, 54, 55, 56, 97, 98, 211, … |
| graph-005 | Explain quantum tunnelling in terms of concepts I've al… | multihop | 0.250 | 0.059 | 0.000 | 0.000 | 881, 670, 655 | 685, 686, 687, 688 |
| graph-006 | What concepts connect thermodynamics and statistical me… | multihop | 0.100 | 1.000 | 0.333 | 0.454 | 709, 70, 728 | 706, 707, 708, 709, 710, 726, 727, 728, … |
| graph-007 | How does the concept of fields unify electricity, magne… | multihop | 0.118 | 0.250 | 0.333 | 0.247 | 286, 210, 243 | 485, 486, 487, 488, 489, 490, 491, 492, … |

## Config

- **Tenant:** global
- **Collection:** knowledge_base
- **Embedder:** jinaai/jina-embeddings-v3
- **SPLADE:** True
- **Reranker:** False
- **Score threshold:** 0.45
- **Judge:** claude-3-haiku-20240307
- **Elapsed:** 375.9s
