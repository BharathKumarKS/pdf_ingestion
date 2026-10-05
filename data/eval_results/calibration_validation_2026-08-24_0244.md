# Calibration Validation

**2026-08-24T02:44:54+00:00**  
Judge: openai / Qwen/Qwen3-VL-8B-Instruct

## Summary

| ID | Query | Labeled pages | YES | PARTIAL | NO | ERROR |
| --- | --- | --- | --- | --- | --- | --- |
| vec-001 | What is the formula for kinetic energy? | 95, 252 | 1 | 1 | 0 | 0 |
| vec-002 | Define Newton's first law of motion | 178, 179 | 0 | 0 | 2 | 0 |
| vec-003 | What is the value of Planck's constant? | 965 | 1 | 0 | 0 | 0 |
| vec-004 | What does Feynman say about the principle of least acti… | 452, 456, 460, 466 | 0 | 1 | 3 | 0 |
| vec-005 | What is the difference between elastic and inelastic co… | 207, 208, 209 | 0 | 2 | 1 | 0 |
| vec-006 | What is Newton's second law of motion? | 179, 180, 181 | 2 | 0 | 1 | 0 |
| vec-007 | What is the formula for gravitational force? | 242, 243 | 0 | 1 | 1 | 0 |
| vec-008 | Define momentum | 178, 179 | 0 | 2 | 0 | 0 |
| vec-009 | What is the work-energy theorem? | 267, 268, 269, 270 | 1 | 1 | 2 | 0 |
| vec-010 | What is the uncertainty principle? | 668, 669, 670, 671, 672 | 0 | 3 | 2 | 0 |
| raptor-001 | Give me an overview of how classical mechanics breaks d… | 349, 686, 693 | 0 | 3 | 0 | 0 |
| raptor-002 | Summarize the key themes in the chapter on conservation… | 97, 98, 211, 212 | 0 | 3 | 1 | 0 |
| raptor-003 | How does Feynman build up the concept of energy from me… | 252, 730, 786, 800 | 1 | 2 | 1 | 0 |
| raptor-004 | What are the main ideas connecting electricity and magn… | 487, 490, 492 | 0 | 2 | 1 | 0 |
| raptor-005 | How does the textbook introduce probability into physic… | 124, 670, 673 | 1 | 1 | 1 | 0 |
| raptor-006 | How does Feynman explain the relationship between force… | 278, 279, 280 | 0 | 2 | 1 | 0 |
| graph-001 | Why does a satellite stay in orbit? | 142, 143, 274 | 0 | 3 | 0 | 0 |
| graph-002 | What should I understand before learning about Maxwell'… | 487, 488, 489 | 0 | 2 | 1 | 0 |
| graph-003 | How is simple harmonic motion related to wave propagati… | 384, 385, 870 | 0 | 3 | 0 | 0 |
| graph-004 | How do conservation laws appear across different areas … | 97, 211, 213 | 0 | 3 | 0 | 0 |
| graph-005 | What connects the inverse square law in gravity and ele… | 143, 144, 242, 243 | 0 | 4 | 0 | 0 |
| graph-006 | What concepts connect thermodynamics and statistical me… | 709, 728, 729 | 0 | 3 | 0 | 0 |
| graph-007 | How does the concept of fields unify electricity, magne… | 487, 488, 580 | 0 | 2 | 1 | 0 |

## Per-Page Verdicts

| ID | Page | Verdict | Reason |
| --- | --- | --- | --- |
| vec-001 | 95 | YES | The page directly provides the kinetic energy formula K.E. = WV²/2g, which answe… |
| vec-001 | 252 | PARTIAL | The page discusses the rate of change of kinetic energy and its relation to work… |
| vec-002 | 178 | NO | The page discusses momentum and inertia but does not define Newton's first law o… |
| vec-002 | 179 | NO | The page discusses Newton’s Second Law and acceleration, not the first law, whic… |
| vec-003 | 965 | YES | The page explicitly defines Planck’s constant with its numerical value (6.626068… |
| vec-004 | 452 | NO | This page discusses the principle of least time in optics, not Feynman’s views o… |
| vec-004 | 456 | NO | The page discusses Snell’s law and historical context of light refraction, not F… |
| vec-004 | 460 | PARTIAL | The page discusses Fermat’s principle of least time and its application to refra… |
| vec-004 | 466 | NO | The page discusses Fermat’s principle of least time and its relation to the spee… |
| vec-005 | 207 | PARTIAL | The page describes the compression and rebound of bodies during collision, hinti… |
| vec-005 | 208 | PARTIAL | The page discusses elastic collisions and gives an example involving equal-mass … |
| vec-005 | 209 | NO | This page discusses relativistic momentum and mass, which is unrelated to the cl… |
| vec-006 | 179 | YES | The page directly states Newton’s Second Law as F = ma and explains its implicat… |
| vec-006 | 180 | NO | The page discusses velocity components and displacement but does not mention New… |
| vec-006 | 181 | YES | The page directly states Newton’s Second Law in component form (Fx = max, etc.),… |
| vec-007 | 242 | NO | The page discusses electric force and electric fields, not gravitational force, … |
| vec-007 | 243 | PARTIAL | The page mentions the formula for gravitational force as "force equals mass time… |
| vec-008 | 178 | PARTIAL | The page begins to define momentum and contrasts it with velocity, but it does n… |
| vec-008 | 179 | PARTIAL | The page discusses momentum in the context of force and Newton’s Second Law but … |
| vec-009 | 267 | NO | The page begins a discussion on work and potential energy but is truncated and d… |
| vec-009 | 268 | PARTIAL | The page begins to introduce the concept of work in physics but is truncated and… |
| vec-009 | 269 | NO | The page discusses the distinction between physiological and physical work but d… |
| vec-009 | 270 | YES | The page directly states that work done on a particle equals the change in its k… |
| vec-010 | 668 | PARTIAL | The page mentions the uncertainty principle in the context of quantum mechanics … |
| vec-010 | 669 | PARTIAL | The page introduces quantum mechanics concepts and mentions “ideal experiments,”… |
| vec-010 | 670 | NO | This page discusses probability amplitudes and interference in quantum mechanics… |
| vec-010 | 671 | NO | The page discusses electron behavior in a double-slit experiment and the failure… |
| vec-010 | 672 | PARTIAL | The page discusses the uncertainty principle in the context of measuring momentu… |
| raptor-001 | 349 | PARTIAL | The page introduces the idea that classical mechanics (like Newton’s laws) emerg… |
| raptor-001 | 686 | PARTIAL | The page touches on how classical expectations (like electrons and protons colla… |
| raptor-001 | 693 | PARTIAL | The page acknowledges that classical mechanics fails at atomic scales due to the… |
| raptor-002 | 97 | PARTIAL | The page introduces conservation of energy and hints at other conservation laws … |
| raptor-002 | 98 | PARTIAL | The page introduces key conservation laws (charge, baryons, leptons) relevant to… |
| raptor-002 | 211 | NO | The page is too fragmented and lacks coherent discussion of conservation laws, o… |
| raptor-002 | 212 | PARTIAL | The page introduces the concept of symmetry in physics, which is foundational to… |
| raptor-003 | 252 | YES | This page directly illustrates Feynman’s derivation of mechanical energy conserv… |
| raptor-003 | 730 | PARTIAL | The page introduces Brownian motion and equipartition of energy, which are therm… |
| raptor-003 | 786 | NO | This page discusses a rudimentary heat engine and Carnot’s contributions to ther… |
| raptor-003 | 800 | PARTIAL | The page discusses the relationship between heat and temperature in reversible e… |
| raptor-004 | 487 | PARTIAL | The page introduces the Lorentz force law and superposition principle, which are… |
| raptor-004 | 490 | NO | This page discusses radiation from accelerating charges and the derivation of el… |
| raptor-004 | 492 | PARTIAL | The page discusses charge movement and acceleration in wires driven by a generat… |
| raptor-005 | 124 | PARTIAL | The page discusses experimental results and distribution of outcomes, hinting at… |
| raptor-005 | 670 | YES | This page directly explains how probability is introduced in quantum physics thr… |
| raptor-005 | 673 | NO | The page discusses the limitations of measuring position and momentum in quantum… |
| raptor-006 | 278 | PARTIAL | The page introduces potential energy and fields but does not explicitly explain … |
| raptor-006 | 279 | NO | This page discusses potential energy in terms of Ψ(x, y, z) and its relation to … |
| raptor-006 | 280 | PARTIAL | The page begins to explain how zero work implies zero force via potential energy… |
| graph-001 | 142 | PARTIAL | The page introduces the historical context and principle of inertia, which is fo… |
| graph-001 | 143 | PARTIAL | The page discusses Newton’s law of gravitation and its relation to planetary mot… |
| graph-001 | 274 | PARTIAL | The page discusses escape velocity and orbital velocity but cuts off mid-explana… |
| graph-002 | 487 | PARTIAL | The page introduces the Lorentz force law and superposition principle, which are… |
| graph-002 | 488 | PARTIAL | The page touches on retarded time and the finite speed of light, which are found… |
| graph-002 | 489 | NO | The page discusses quantum mechanics, radioactivity, and nuclear forces, which a… |
| graph-003 | 384 | PARTIAL | The page explains the connection between circular motion and simple harmonic mot… |
| graph-003 | 385 | PARTIAL | The page discusses mathematical methods for analyzing simple harmonic motion but… |
| graph-003 | 870 | PARTIAL | The page discusses wave solutions and sinusoidal behavior in a vibrating string,… |
| graph-004 | 97 | PARTIAL | The page introduces conservation of energy and hints at other conservation laws … |
| graph-004 | 211 | PARTIAL | The page mentions conservation of momentum in quantum mechanics but does not sys… |
| graph-004 | 213 | PARTIAL | The page discusses symmetry and the conditions under which physical laws remain … |
| graph-005 | 143 | PARTIAL | The page introduces the inverse square relationship in gravity but does not conn… |
| graph-005 | 144 | PARTIAL | The page discusses Newton’s verification of gravitational force using the moon’s… |
| graph-005 | 242 | PARTIAL | The page explains the electric field and its relation to force via Coulomb’s law… |
| graph-005 | 243 | PARTIAL | The page introduces the concept of fields and how mass and charge respond to gra… |
| graph-006 | 709 | PARTIAL | The page discusses energy distribution in molecular motion but does not explicit… |
| graph-006 | 728 | PARTIAL | The page introduces the Boltzmann distribution, which connects microscopic state… |
| graph-006 | 729 | PARTIAL | The page discusses how increasing temperature leads to classical behavior in qua… |
| graph-007 | 487 | PARTIAL | The page introduces the unifying role of electric and magnetic fields via the Lo… |
| graph-007 | 488 | PARTIAL | The page discusses retarded time and how fields depend on past charge behavior, … |
| graph-007 | 580 | NO | The page discusses light reflection and polarization, which is related to electr… |

## Queries Needing Attention

- **vec-002** — labeled [178, 179]: p178=NO; p179=NO
- **vec-004** — labeled [452, 456, 460, 466]: p452=NO; p456=NO; p460=PARTIAL; p466=NO
- **vec-005** — labeled [207, 208, 209]: p207=PARTIAL; p208=PARTIAL; p209=NO
- **vec-006** — labeled [179, 180, 181]: p179=YES; p180=NO; p181=YES
- **vec-007** — labeled [242, 243]: p242=NO; p243=PARTIAL
- **vec-009** — labeled [267, 268, 269, 270]: p267=NO; p268=PARTIAL; p269=NO; p270=YES
- **vec-010** — labeled [668, 669, 670, 671, 672]: p668=PARTIAL; p669=PARTIAL; p670=NO; p671=NO; p672=PARTIAL
- **raptor-002** — labeled [97, 98, 211, 212]: p97=PARTIAL; p98=PARTIAL; p211=NO; p212=PARTIAL
- **raptor-003** — labeled [252, 730, 786, 800]: p252=YES; p730=PARTIAL; p786=NO; p800=PARTIAL
- **raptor-004** — labeled [487, 490, 492]: p487=PARTIAL; p490=NO; p492=PARTIAL
- **raptor-005** — labeled [124, 670, 673]: p124=PARTIAL; p670=YES; p673=NO
- **raptor-006** — labeled [278, 279, 280]: p278=PARTIAL; p279=NO; p280=PARTIAL
- **graph-002** — labeled [487, 488, 489]: p487=PARTIAL; p488=PARTIAL; p489=NO
- **graph-007** — labeled [487, 488, 580]: p487=PARTIAL; p488=PARTIAL; p580=NO
