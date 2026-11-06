# ColPali visual-search test cases — all 33 (`vis-*`)

App: http://localhost:8503 → tab **🖼️ Visual Search**. Paste one query at a time.
⚠️ These 33 carry **no labels**, so the lane is populated but **not measurable** — treat this as a
smoke/demo pass, not a scored run. The current doc (`7ba61432`) now has 968 ColPali page vectors.

## Chapter 1–3
 1. vis-001  Show me the figure that displays water magnified one billion times.
 2. vis-002  Show me the schematic diagram of DNA from Fig. 3-2.

## Chapter 4–8 (mechanics)
 3. vis-003  Show me the diagram of a pendulum (Fig. 4-7) that displays the bob, string, and the angle of swing.
 4. vis-005  Show me the graph that plots the fraction of heads versus the number of tosses N for a particular sequence of penny tosses.
 5. vis-006  Show me the diagram of the apparatus that demonstrates the independence of vertical and horizontal motions.
 6. vis-007  Locate the figure that illustrates the Cavendish torsion balance apparatus, showing the horizontal rod with two small masses suspended by a wire, and the two large masses positioned nearby to create the gravitational attraction for measuring G.
 7. vis-008  Show me the diagram of a parabolic trajectory of a falling body launched with an initial horizontal velocity, including axes labeled \(x\) and \(y\) and the parabola curve (Fig. 8-4).

## Chapter 10–14 (conservation, vectors, relativity)
 8. vis-010  Find the figure that illustrates the addition of vectors by placing the tail of one vector at the head of the other, forming a parallelogram.
 9. vis-011  Show me the diagram of the closed path in a gravitational field from Fig. 13-3.
10. vis-012  Show the diagram that illustrates the coordinate transformation between the stationary system and the moving system (the primed and unprimed coordinate axes) used to demonstrate that Newton's laws retain the same form in both frames.
11. vis-013  Show me the diagram of the torque produced by a force, including the force vector, the point of application, the lever arm, and the angle between the force direction and the lever arm.
12. vis-014  Show me the diagram illustrating the two coordinate systems where the z- and z′-axes coincide and one system is rotated by a fixed angle θ relative to the other.
13. vis-015  Show me the figure of the actual motion of the tip of the axis of the gyroscope under gravity after the axis was released.

## Chapter 26–36 (optics, waves, the eye)
14. vis-018  Show me the figure of a light ray reflecting off a surface where the angle of incidence equals the angle of reflection.
15. vis-019  Show me the diagram of the paraboloidal mirror, including its focal point and axis of symmetry.
16. vis-020  Show me the diagram of a thin lens with two positive radii, including the labels for the lens surfaces and the two positive radii of curvature.
17. vis-021  Show me the diagram of the two-antenna system (Fig. 29-6) that illustrates the amplitude pattern with the N antenna one-quarter wavelength apart from the S antenna and one-fourth period behind it, indicating that the W direction has amplitude 2 and the S direction has amplitude 0.
18. vis-022  Find the figure that shows a linear array of n equal oscillators driven with phases s = s.
19. vis-026  Show me the diagram of a charged particle moving in a circular (or helical) path in a uniform magnetic field, including the velocity vector, magnetic field direction, and radius of curvature.
20. vis-027  Show me the diagram of the wavefronts of a wave traveling at an angle to the coordinate axes, as illustrated in Fig. 34-11.
21. vis-028  Locate the figure that shows the spectral sensitivity of the eye, with a dashed curve for rods and a solid curve for cones, as plotted in Fig. 35-3.
22. vis-029  Show me the diagram of the neural connections from the eyes to the visual cortex.
23. vis-030  Show me the graph that displays the response to light of the nerve fibers of the horseshoe crab's eye, as presented in Fig. 36-12.

## Chapter 38–41 (quantum, thermodynamics, statistics)
24. vis-031  Show me Fig. 38-2, the diagram of the single-slit experiment illustrating the relationship between particle position and vertical momentum components.
25. vis-032  Show me the diagram of the gas box with a piston, labeled V, as depicted in Fig. 39-1.
26. vis-033  Show me the diagram of the velocity distribution function (Fig. 40-5) that displays the shaded area labeled f(u) du.
27. vis-034  Show me the diagram of the 36-step random walk of step length l, starting at point B and ending at S36, as illustrated in Figure 41-6.

## Chapter 44–51 (entropy, waves, phase velocity)
28. vis-035  Show me the figure of the heated rubber band (Fig. 44-1).
29. vis-036  Show me the figure that illustrates the change in entropy during a reversible transformation.
30. vis-037  Show me the figure that displays the electric field as a function of position with a solid curve for one instant and a dashed curve for a later instant.
31. vis-038  Show me the frequency spectrum diagram of a carrier wave modulated by a single cosine wave, including the sideband frequencies ωc ± ωm.
32. vis-039  Show me the schematic diagram (Fig. 50-2) that depicts a periodic function f(t) as a sum of simple harmonic functions, including the amplitudes aₙ and bₙ.
33. vis-040  Show me the graph of phase velocity versus wavelength for water.

---

## Also available: synthetic images for the aperture/domain test
`logs/p1/step10/gen_concept_images.py` writes synthetic figures to `logs/p1/step10/concept_images/`:
* IN-DOMAIN (Vol 1 concepts: waves, interference, diffraction, blackbody, oscillator, resonance,
  pendulum, energy conservation),
* NEAR-DOMAIN (physics-looking but NOT Vol 1: atomic orbital, EM wave/Maxwell, a molecule, a
  financial line chart) — the adversarial aperture test,
* FAR-DOMAIN (noise + gradient).

These are for `visual_lane_validation.py` (the three-way split + aperture sweep), which is the
pending step from the ColPali write — not the demo tab.

## Full sample page images on disk
`data/page_images/7ba61432-c5e0-416d-aecf-25a232523481/` — 968 PNGs (`page_0001.png` … `page_0968.png`),
the current doc's rasterized pages, written today.
