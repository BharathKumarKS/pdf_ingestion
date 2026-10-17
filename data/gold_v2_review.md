# Gold v2 — human verification sheet (P0-9 Session 5 / Task 7)

Generated from `data/eval_queries_v2.json` by `scripts/build_review_sheet.py` (6 per stratum). Fill the **verdict** column.

## How to check each row

1. Open `data/base_textbooks/feynman-lectures-on-physics-volume1.pdf`.
2. Go to each page in **pages to open** and read it against the row's criterion.
3. **The DB page number carries ±1 of chunk-boundary fuzz (§D4).** A page counts
   as correct if the content is on the listed page **or within ±1 of it** — glance
   at the neighbours before calling it wrong. Record `WRONG` only when the content
   is absent across that window.
4. Verdicts: `OK` · `WRONG` (a listed page does not support the query — over-labelled) · `MISSING-PAGE` (the answer is on a page NOT listed — under-labelled; **write that page in notes**) · negatives also use `ANSWERABLE`.
5. An error is `WRONG`, `MISSING-PAGE` or `ANSWERABLE`. `OK` is the only pass.

## Sample: 6 per stratum = 30 queries

| stratum | population | sampled | criterion |
|---|---|---|---|
| factual (answerable) | 53 | 6 | Is the answer on the listed page? |
| multihop (answerable) | 40 | 6 | Do the listed pages establish BOTH concepts and the link between them? |
| overview (answerable) | 40 | 6 | Does the page CONTRIBUTE to the topic's synthesis? (not: does it answer a question) |
| visual (answerable) | 33 | 6 | Does the page SHOW the figure/table described? (a different figure is WRONG) |
| negatives (must be unanswerable) | 34 | 6 | Is the book genuinely unable to answer this? Any page that does = ANSWERABLE |

## factual (answerable)

*Is the answer on the listed page?*

| id | query | labels | pages to open | verdict | notes |
|---|---|---|---|---|---|
| gold-003 | Which section number is titled 'Thermionic emission'? | 1 | 30 | | |
| gold-025 | According to Einstein's modification of Newton's laws, what replaces the old \(m v\) as… | 18 | 298, 302, 317, 330, 344  (of 18 labelled) | | |
| gold-033 | According to the passage, what mathematical function of time is the displacement of a m… | 8 | 187, 384, 430, 431, 445  (of 8 labelled) | | |
| gold-040 | Which dial is associated with changing the stiffness of the spring? | 1 | 450 | | |
| gold-052 | In Fig. 34-1, what does the point A represent? | 1 | 589 | | |
| gold-067 | What term does the passage use to refer to the majority of molecules in a gas? | 9 | 131, 694, 713, 728, 771  (of 9 labelled) | | |

## multihop (answerable)

*Do the listed pages establish BOTH concepts and the link between them?*

| id | query | labels | pages to open | verdict | notes |
|---|---|---|---|---|---|
| gold-008 | How did astronomers discover that stars are made of atoms of the same kind as those on … | 1 | 79 | | |
| gold-027 | Why does the passage state that we look at the 'blob' from different points of view whe… | 13 | 285, 310, 320, 331, 606  (of 13 labelled) | | |
| gold-038 | Why, according to the passage, does the force only need to fight friction to keep an ef… | 1 | 427 | | |
| gold-062 | How many independent directions contribute to the total kinetic energy of a gas particl… | 6 | 698, 707, 708, 710, 711  (of 6 labelled) | | |
| gold-085 | How does the compressibility of radiation influence the motion of a Foucault pendulum i… | 3 | 30, 490, 921 | | |
| gold-097 | How does the energy-time uncertainty principle affect the determination of the average … | 3 | 118, 707, 831 | | |

## overview (answerable)

*Does the page CONTRIBUTE to the topic's synthesis? (not: does it answer a question)*

| id | query | labels | pages to open | verdict | notes |
|---|---|---|---|---|---|
| ovw-006 | How does Feynman build up the concept of quantum probability amplitudes throughout Volu… · topic: Quantum Probability Amplitudes | 46 | 30, 527, 661, 674, 932  (of 46 labelled) | | |
| ovw-009 | How does Feynman develop the kinetic theory of gases throughout Volume 1, connecting mi… · topic: Kinetic Theory of Gases | 127 | 31, 699, 730, 779, 849  (of 127 labelled) | | |
| ovw-024 | How does Feynman develop the concept of rotational dynamics throughout Volume 1, linkin… · topic: Rotational Dynamics | 36 | 146, 344, 360, 369, 932  (of 36 labelled) | | |
| ovw-027 | How does Feynman develop the concept of diffusion from the microscopic random motion of… · topic: Diffusion | 35 | 31, 697, 746, 773, 834  (of 35 labelled) | | |
| ovw-029 | How does Feynman's treatment of color vision evolve throughout The Feynman Lectures on … · topic: Color Vision | 34 | 610, 619, 628, 639, 651  (of 34 labelled) | | |
| ovw-047 | How does Feynman's treatment of the interaction of light with matter evolve throughout … · topic: Interaction of Light with Matter | 95 | 30, 535, 600, 677, 932  (of 95 labelled) | | |

## visual (answerable)

*Does the page SHOW the figure/table described? (a different figure is WRONG)*

| id | query | labels | pages to open | verdict | notes |
|---|---|---|---|---|---|
| vis-005 | Show me the graph that plots the fraction of heads versus the number of tosses N for a … | 1 | 130 | | |
| vis-008 | Show me the diagram of a parabolic trajectory of a falling body launched with an initia… | 1 | 176 | | |
| vis-012 | Show the diagram that illustrates the coordinate transformation between the stationary … | 4 | 214, 217, 218, 285 | | |
| vis-013 | Show the diagram of the torque produced by a force, including the force vector, the poi… | 1 | 339 | | |
| vis-020 | Show me the diagram of a thin lens with two positive radii, including the labels for th… | 1 | 477 | | |
| vis-027 | Show me the diagram of the wavefronts of a wave traveling at an angle to the coordinate… | 1 | 604 | | |

## negatives (must be unanswerable)

*Is the book genuinely unable to answer this? Any page that does = ANSWERABLE*

| id | query | labels | pages to open | verdict | notes |
|---|---|---|---|---|---|
| neg-in_-001 | What does the book say about the Schrödinger equation for the hydrogen atom? | 0 | — (must be unanswerable) | | |
| neg-in_-002 | What is the book's treatment of general relativity and curved spacetime? | 0 | — (must be unanswerable) | | |
| neg-in_-006 | What is the book's derivation of the Navier-Stokes equations? | 0 | — (must be unanswerable) | | |
| neg-in_-009 | What does the book say about the quantum Hall effect? | 0 | — (must be unanswerable) | | |
| neg-nea-005 | What value does the book use for the cosmological constant? | 0 | — (must be unanswerable) | | |
| neg-out-002 | Who wrote Pride and Prejudice? | 0 | — (must be unanswerable) | | |

---

## Scoring

```bash
uv run python scripts/score_review_sheet.py
```

Record the result in `IMPROVEMENTS.md` §F4b as `label error rate = X/N = Y%`, with the per-stratum breakdown.
