# Calibration Validation

**2026-08-24T02:44:33+00:00**  
Judge: openai / Qwen/Qwen3-VL-8B-Instruct

## Summary

| ID | Query | Labeled pages | YES | PARTIAL | NO | ERROR |
| --- | --- | --- | --- | --- | --- | --- |
| vec-001 | What is the formula for kinetic energy? | 95, 252 | 1 | 1 | 0 | 0 |
| vec-002 | Define Newton's first law of motion | 178, 179 | 0 | 0 | 2 | 0 |
| vec-003 | What is the value of Planck's constant? | 965 | 1 | 0 | 0 | 0 |
| vec-004 | What does Feynman say about the principle of least acti… | 452, 456, 460, 466 | 0 | 1 | 3 | 0 |
| vec-005 | What is the difference between elastic and inelastic co… | 207, 208, 209 | 0 | 2 | 1 | 0 |
| vec-006 | What is Newton's second law of motion? | 179, 180, 181 | 1 | 1 | 1 | 0 |
| vec-007 | What is the formula for gravitational force? | 242, 243 | 0 | 1 | 1 | 0 |
| vec-008 | Define momentum | 178, 179 | 0 | 2 | 0 | 0 |
| vec-009 | What is the work-energy theorem? | 267, 268, 269, 270 | 1 | 0 | 3 | 0 |
| vec-010 | What is the uncertainty principle? | 668, 669, 670, 671, 672 | 0 | 3 | 2 | 0 |
| raptor-001 | Give me an overview of how classical mechanics breaks d… | 349, 686, 693 | 1 | 2 | 0 | 0 |
| raptor-002 | Summarize the key themes in the chapter on conservation… | 97, 98, 211, 212 | 0 | 3 | 1 | 0 |
| raptor-003 | How does Feynman build up the concept of energy from me… | 252, 730, 786, 800 | 1 | 2 | 1 | 0 |
| raptor-004 | What are the main ideas connecting electricity and magn… | 487, 490, 492 | 0 | 2 | 1 | 0 |
| raptor-005 | How does the textbook introduce probability into physic… | 124, 670, 673 | 1 | 1 | 1 | 0 |
| raptor-006 | How does Feynman explain the relationship between force… | 278, 279, 280 | 0 | 2 | 1 | 0 |
| graph-001 | Why does a satellite stay in orbit? | 142, 143, 274 | 0 | 3 | 0 | 0 |
| graph-002 | What should I understand before learning about Maxwell'… | 487, 488, 489 | 0 | 2 | 1 | 0 |
| graph-003 | How is simple harmonic motion related to wave propagati… | 384, 385, 870 | 0 | 3 | 0 | 0 |
| graph-004 | How do conservation laws appear across different areas … | 97, 211, 213 | 0 | 2 | 1 | 0 |
| graph-005 | What connects the inverse square law in gravity and ele… | 143, 144, 242, 243 | 0 | 4 | 0 | 0 |
| graph-006 | What concepts connect thermodynamics and statistical me… | 709, 728, 729 | 0 | 3 | 0 | 0 |
| graph-007 | How does the concept of fields unify electricity, magne… | 487, 488, 580 | 0 | 2 | 1 | 0 |

## Per-Page Verdicts

| ID | Page | Verdict | Reason |
| --- | --- | --- | --- |
| vec-001 | 95 | YES | The page directly provides the kinetic energy formula K.E. = WV²/2g, which answe… |
| vec-001 | 252 | PARTIAL | The page discusses the rate of change of kinetic energy and its relationship to … |
| vec-002 | 178 | NO | The page discusses momentum and mass vs. weight/inertia but does not define Newt… |
| vec-002 | 179 | NO | The page discusses Newton’s Second Law and acceleration, not the first law, whic… |
| vec-003 | 965 | YES | The page directly provides the value of Planck’s constant as h = 6.62606896 × 10… |
| vec-004 | 452 | NO | This page discusses optics and the principle of least time, not Feynman’s views … |
| vec-004 | 456 | NO | The page discusses Snell’s law and the historical development of physical laws, … |
| vec-004 | 460 | PARTIAL | The page discusses Fermat’s principle of least time and its application to Snell… |
| vec-004 | 466 | NO | The page discusses Fermat’s principle of least time and its relation to the spee… |
| vec-005 | 207 | PARTIAL | The page describes the compression and rebound of bodies during collision, hinti… |
| vec-005 | 208 | PARTIAL | The page discusses elastic collisions and gives an example involving equal-mass … |
| vec-005 | 209 | NO | The page discusses relativistic momentum and mass variation with velocity, which… |
| vec-006 | 179 | YES | The page directly states Newton’s Second Law as F = ma and explains that force c… |
| vec-006 | 180 | NO | The page discusses displacement and velocity components but does not mention New… |
| vec-006 | 181 | PARTIAL | The page explains Newton’s Second Law in component form (Fx = max, etc.), which … |
| vec-007 | 242 | NO | The page discusses electric force and electric fields, not gravitational force, … |
| vec-007 | 243 | PARTIAL | The page mentions the formula for gravitational force (force = mass × gravitatio… |
| vec-008 | 178 | PARTIAL | The page introduces the concept of momentum and contrasts it with velocity, but … |
| vec-008 | 179 | PARTIAL | The page discusses momentum in the context of force and Newton’s Second Law but … |
| vec-009 | 267 | NO | The page begins a discussion on work and potential energy but is truncated and d… |
| vec-009 | 268 | NO | The page begins discussing the concept of work in physics but is truncated and d… |
| vec-009 | 269 | NO | The page discusses the distinction between physiological and physical work but d… |
| vec-009 | 270 | YES | The page directly states the work-energy theorem by explaining that the work don… |
| vec-010 | 668 | PARTIAL | The page mentions the uncertainty principle in the context of quantum mechanics … |
| vec-010 | 669 | PARTIAL | The page introduces quantum mechanics concepts and mentions “ideal experiments” … |
| vec-010 | 670 | NO | This page discusses probability amplitudes and interference in quantum mechanics… |
| vec-010 | 671 | NO | The page discusses electron behavior in a double-slit experiment and the failure… |
| vec-010 | 672 | PARTIAL | The page mentions the uncertainty principle in passing but focuses on an experim… |
| raptor-001 | 349 | PARTIAL | The page introduces the idea that classical mechanics (Newton’s laws) emerges fr… |
| raptor-001 | 686 | PARTIAL | The page touches on how classical expectations (like electrons and protons colla… |
| raptor-001 | 693 | YES | The page directly states that classical mechanics fails at atomic scales because… |
| raptor-002 | 97 | PARTIAL | The page mentions conservation of energy and introduces conservation of linear a… |
| raptor-002 | 98 | PARTIAL | The page introduces key conservation laws (charge, baryons, leptons) relevant to… |
| raptor-002 | 211 | NO | The page is too truncated and lacks coherent content to summarize key themes in … |
| raptor-002 | 212 | PARTIAL | The page introduces the concept of symmetry in physics, which is foundational to… |
| raptor-003 | 252 | YES | This page directly illustrates Feynman’s derivation of mechanical energy conserv… |
| raptor-003 | 730 | PARTIAL | The page introduces Brownian motion and equipartition of energy, which are key t… |
| raptor-003 | 786 | NO | This page discusses a heat engine example and mentions Carnot’s work but does no… |
| raptor-003 | 800 | PARTIAL | The page discusses entropy and reversible engines, which are key to connecting m… |
| raptor-004 | 487 | PARTIAL | The page introduces the Lorentz force law and superposition principle, which are… |
| raptor-004 | 490 | NO | The page discusses radiation from accelerating charges and electromagnetic field… |
| raptor-004 | 492 | PARTIAL | The page discusses charge movement and acceleration in wires driven by a generat… |
| raptor-005 | 124 | PARTIAL | The page discusses statistical outcomes from coin tosses and hints at probabilit… |
| raptor-005 | 670 | YES | This page directly explains how probability is introduced in quantum physics thr… |
| raptor-005 | 673 | NO | The page discusses the limitations in measuring position and momentum in quantum… |
| raptor-006 | 278 | PARTIAL | The page introduces potential energy and fields but does not explicitly explain … |
| raptor-006 | 279 | NO | This page discusses potential energy in terms of Ψ (a scalar potential) and its … |
| raptor-006 | 280 | PARTIAL | The page introduces the concept that zero work implies no force, linking potenti… |
| graph-001 | 142 | PARTIAL | The page introduces the concept of inertia and historical context but does not e… |
| graph-001 | 143 | PARTIAL | The page discusses Newton’s understanding of gravitational forces and Kepler’s l… |
| graph-001 | 274 | PARTIAL | The page discusses escape velocity and orbital velocity but cuts off mid-explana… |
| graph-002 | 487 | PARTIAL | The page introduces the Lorentz force law and superposition principle, which are… |
| graph-002 | 488 | PARTIAL | The page discusses retarded time and how fields depend on past charge behavior, … |
| graph-002 | 489 | NO | The page discusses quantum mechanics, radioactivity, and nuclear forces, which a… |
| graph-003 | 384 | PARTIAL | The page explains the connection between circular motion and simple harmonic mot… |
| graph-003 | 385 | PARTIAL | The page discusses initial conditions and mathematical representation of oscilla… |
| graph-003 | 870 | PARTIAL | The page discusses wave solutions and sinusoidal behavior in a vibrating string,… |
| graph-004 | 97 | PARTIAL | The page mentions conservation of energy, linear momentum, and angular momentum,… |
| graph-004 | 211 | NO | The page snippet is too fragmented and lacks context to meaningfully address how… |
| graph-004 | 213 | PARTIAL | The page discusses symmetry and invariance in physical laws, which relates to co… |
| graph-005 | 143 | PARTIAL | The page introduces the inverse square relationship in gravity but does not conn… |
| graph-005 | 144 | PARTIAL | The page discusses Newton’s verification of gravitational force via the moon’s o… |
| graph-005 | 242 | PARTIAL | The page explains the electric field and its relation to force via Coulomb’s law… |
| graph-005 | 243 | PARTIAL | The page mentions both gravity and electricity in the context of fields and forc… |
| graph-006 | 709 | PARTIAL | The page discusses energy distribution in molecular motion but does not explicit… |
| graph-006 | 728 | PARTIAL | The page introduces the Boltzmann distribution, which connects microscopic energ… |
| graph-006 | 729 | PARTIAL | The page discusses the transition from quantum to classical behavior with temper… |
| graph-007 | 487 | PARTIAL | The page introduces the unifying role of electric and magnetic fields via the Lo… |
| graph-007 | 488 | PARTIAL | The page discusses retarded time and field propagation at speed c, which is rele… |
| graph-007 | 580 | NO | The page discusses light reflection and polarization, but does not address how f… |

## Queries Needing Attention

- **vec-002** — labeled [178, 179]: p178=NO; p179=NO
- **vec-004** — labeled [452, 456, 460, 466]: p452=NO; p456=NO; p460=PARTIAL; p466=NO
- **vec-005** — labeled [207, 208, 209]: p207=PARTIAL; p208=PARTIAL; p209=NO
- **vec-006** — labeled [179, 180, 181]: p179=YES; p180=NO; p181=PARTIAL
- **vec-007** — labeled [242, 243]: p242=NO; p243=PARTIAL
- **vec-009** — labeled [267, 268, 269, 270]: p267=NO; p268=NO; p269=NO; p270=YES
- **vec-010** — labeled [668, 669, 670, 671, 672]: p668=PARTIAL; p669=PARTIAL; p670=NO; p671=NO; p672=PARTIAL
- **raptor-002** — labeled [97, 98, 211, 212]: p97=PARTIAL; p98=PARTIAL; p211=NO; p212=PARTIAL
- **raptor-003** — labeled [252, 730, 786, 800]: p252=YES; p730=PARTIAL; p786=NO; p800=PARTIAL
- **raptor-004** — labeled [487, 490, 492]: p487=PARTIAL; p490=NO; p492=PARTIAL
- **raptor-005** — labeled [124, 670, 673]: p124=PARTIAL; p670=YES; p673=NO
- **raptor-006** — labeled [278, 279, 280]: p278=PARTIAL; p279=NO; p280=PARTIAL
- **graph-002** — labeled [487, 488, 489]: p487=PARTIAL; p488=PARTIAL; p489=NO
- **graph-004** — labeled [97, 211, 213]: p97=PARTIAL; p211=NO; p213=PARTIAL
- **graph-007** — labeled [487, 488, 580]: p487=PARTIAL; p488=PARTIAL; p580=NO
