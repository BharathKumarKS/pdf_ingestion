# p1-step10-retrieval-only

**2026-10-20T04:11:56+00:00**

## Summary

| Scope | Recall@100 | Recall@20 | Hit@20 | Ctx.Prec | MRR | NDCG@20 | Faithfulness | Ans.Relevance | Citation Acc. | n / cal |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Overall | 0.626 | 0.452 | 0.910 | 0.261 | 0.728 | 0.508 | — | — | — | 133/133 |
|   factual | 0.746 | 0.570 | 0.868 | 0.148 | 0.704 | 0.447 | — | — | — | 53/53 |
|   multihop | 0.633 | 0.543 | 0.875 | 0.104 | 0.615 | 0.504 | — | — | — | 40/40 |
|   overview | 0.459 | 0.206 | 1.000 | 0.568 | 0.873 | 0.592 | — | — | — | 40/40 |

**Abstention (negatives):** 28/34 = 0.824 — a negative is handled correctly when the system declines

## Run integrity

- **Generation metrics:** not requested (retrieval-only)

## Per-Query Results

| ID | Query | Type | Recall@100 | Recall@20 | Hit@20 | Ctx.Prec | MRR | NDCG@20 | Retrieved pages | Labeled pages |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gold-003 | Which section number is titled 'Thermionic emission'? | factual | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 34, 757, 761 | 30 |
| gold-004 | What is the title of section 42-4? | factual | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 34, 246, 763 | 30, 86, 795 |
| gold-005 | According to the passage, is it easy to learn all the r… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 0.387 | 169, 408, 507 | 52 |
| gold-008 | How did astronomers discover that stars are made of ato… | multihop | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 0.631 | 78, 79, 549 | 79 |
| gold-009 | According to the passage, how many quarts of water per … | factual | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 98, 499, 86 | 99 |
| gold-010 | According to the passage, how are antibaryons counted? | factual | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 98, 122, 662 | 99 |
| gold-011 | What does the vertical position in Figure 6-4 represent… | factual | 0.333 | 0.000 | 0.000 | 0.000 | 0.015 | 0.000 | 321, 380, 251 | 125, 315, 645 |
| gold-013 | What happens to the focus of an ellipse when it is view… | multihop | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 148, 140, 482 | 150 |
| gold-014 | Which figure is mentioned as indicating that the law of… | factual | 1.000 | 1.000 | 1.000 | 0.200 | 1.000 | 1.000 | 153, 148, 151 | 148, 150, 151, 153 |
| gold-015 | What symbol is used to denote the limit as the time int… | factual | 0.600 | 0.600 | 1.000 | 0.150 | 1.000 | 0.523 | 171, 253, 167 | 171, 175, 178, 181, 720 |
| gold-016 | According to the passage, what does the integral sign ∫… | factual | 0.533 | 0.333 | 1.000 | 0.250 | 1.000 | 0.304 | 793, 738, 810 | 171, 254, 255, 256, 257, 258, 260, 262, … |
| gold-017 | Which principle will be used as the basis for discussin… | factual | 0.743 | 0.457 | 1.000 | 0.800 | 1.000 | 0.856 | 207, 199, 208 | 178, 196, 197, 198, 199, 200, 201, 202, … |
| gold-019 | What is the expression for acceleration described in th… | factual | 0.750 | 0.375 | 1.000 | 0.300 | 0.500 | 0.387 | 225, 172, 184 | 187, 189, 190, 193, 195, 218, 224, 225, … |
| gold-021 | What is the expression for the time rate of change of t… | factual | 0.600 | 0.200 | 1.000 | 0.050 | 1.000 | 0.339 | 252, 254, 251 | 252, 262, 270, 735, 737 |
| gold-022 | According to the passage, what does the term m(dv/dt) r… | factual | 0.400 | 0.400 | 1.000 | 0.100 | 0.500 | 0.174 | 829, 246, 334 | 218, 225, 230, 231, 252 |
| gold-023 | Under what condition is the gravitational field conside… | factual | 0.500 | 0.500 | 1.000 | 0.050 | 1.000 | 0.177 | 714, 305, 256 | 91, 273 |
| gold-024 | Which plane corresponds to the zero potential energy po… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 1.000 | 273, 279, 332 | 273 |
| gold-025 | According to Einstein's modification of Newton's laws, … | factual | 0.833 | 0.333 | 1.000 | 0.300 | 1.000 | 0.287 | 208, 210, 211 | 298, 299, 300, 301, 302, 312, 314, 316, … |
| gold-026 | Under Einstein's modification, what condition must stil… | factual | 0.833 | 0.417 | 1.000 | 0.250 | 1.000 | 0.303 | 198, 208, 197 | 299, 309, 312, 314, 315, 316, 318, 328, … |
| gold-027 | Why does the passage state that we look at the 'blob' f… | multihop | 0.692 | 0.385 | 1.000 | 0.250 | 0.500 | 0.403 | 320, 308, 335 | 285, 293, 309, 310, 313, 315, 320, 321, … |
| gold-028 | What is called a given point (x, y, z, t) in space-time… | factual | 1.000 | 1.000 | 1.000 | 0.200 | 1.000 | 0.463 | 320, 324, 216 | 321, 322, 325, 329 |
| gold-029 | What is the mass of the particle discussed in Fig. 18-3… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 0.631 | 66, 341, 302 | 341 |
| gold-030 | According to the passage, how is the x-component of for… | factual | 0.625 | 0.500 | 1.000 | 0.200 | 0.250 | 0.298 | 142, 180, 181 | 187, 189, 190, 193, 195, 218, 225, 341 |
| gold-031 | What sidewise force must Moe exert to move mass m outwa… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 0.500 | 0.256 | 359, 337, 180 | 360 |
| gold-032 | When a mass moves only along the radius, which quantity… | multihop | 1.000 | 1.000 | 1.000 | 0.050 | 0.250 | 0.270 | 359, 342, 361 | 360 |
| gold-033 | According to the passage, what mathematical function of… | factual | 0.500 | 0.250 | 1.000 | 0.100 | 0.250 | 0.189 | 381, 500, 875 | 187, 195, 384, 429, 430, 431, 435, 445 |
| gold-034 | According to the passage, what experiment can be devise… | factual | 1.000 | 0.500 | 1.000 | 0.050 | 0.111 | 0.264 | 383, 381, 413 | 384, 569 |
| gold-035 | What is the real part of the eighth complex number list… | factual | 1.000 | 0.000 | 0.000 | 0.000 | 0.037 | 0.000 | 509, 406, 659 | 403 |
| gold-036 | What is the imaginary part of the tenth complex number … | factual | 1.000 | 0.000 | 0.000 | 0.000 | 0.067 | 0.000 | 406, 407, 402 | 403 |
| gold-037 | According to the passage, what happens to the stored en… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 0.500 | 421, 388, 427 | 427 |
| gold-038 | Why, according to the passage, does the force only need… | multihop | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 1.000 | 427, 547, 387 | 427 |
| gold-039 | What does turning dial number ten do in terms of shock … | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 1.000 | 450, 394, 402 | 450 |
| gold-040 | Which dial is associated with changing the stiffness of… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 0.631 | 260, 450, 386 | 450 |
| gold-041 | According to the passage, what speed is assumed for lig… | factual | 0.600 | 0.400 | 1.000 | 0.200 | 1.000 | 0.305 | 284, 465, 898 | 458, 460, 465, 472, 473, 536, 538, 539, … |
| gold-042 | By what factor does light travel more slowly in the gla… | factual | 0.800 | 0.500 | 1.000 | 0.250 | 0.500 | 0.426 | 321, 471, 538 | 458, 460, 472, 473, 535, 538, 539, 540, … |
| gold-043 | Which phenomena of light and radio propagation are ment… | factual | 0.333 | 0.116 | 1.000 | 0.400 | 1.000 | 0.483 | 491, 456, 467 | 207, 210, 457, 458, 460, 462, 463, 464, … |
| gold-044 | What was the purpose of writing down the rest of Eq. (2… | factual | 0.209 | 0.060 | 1.000 | 0.400 | 1.000 | 0.434 | 491, 429, 489 | 262, 264, 265, 266, 270, 272, 273, 274, … |
| gold-045 | What is the additional phase due to the time delay betw… | factual | 1.000 | 0.500 | 1.000 | 0.150 | 1.000 | 0.645 | 510, 512, 515 | 505, 510, 511, 512, 515, 516 |
| gold-046 | What does the case α = 0 represent about the relative p… | factual | 1.000 | 0.833 | 1.000 | 0.250 | 1.000 | 0.729 | 510, 382, 570 | 503, 510, 513, 514, 515, 570 |
| gold-047 | According to the passage, at what speed does light appe… | factual | 0.786 | 0.500 | 1.000 | 0.350 | 1.000 | 0.479 | 535, 859, 544 | 458, 460, 465, 466, 472, 473, 534, 535, … |
| gold-048 | According to the passage, why does light appear to trav… | multihop | 0.556 | 0.444 | 1.000 | 0.200 | 1.000 | 0.453 | 535, 311, 861 | 473, 534, 535, 536, 538, 539, 543, 545, … |
| gold-049 | According to the passage, what is the total energy flux… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 1.000 | 557, 257, 804 | 557 |
| gold-050 | For a motion whose acceleration is initially and finall… | factual | 0.750 | 0.750 | 1.000 | 0.150 | 1.000 | 0.491 | 255, 557, 550 | 90, 273, 274, 557 |
| gold-051 | What assumption is made about the detector's distance f… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 0.631 | 488, 589, 497 | 589 |
| gold-052 | In Fig. 34-1, what does the point A represent? | factual | 1.000 | 1.000 | 1.000 | 0.050 | 0.020 | 0.316 | 349, 338, 346 | 589 |
| gold-053 | How many kinds of cells are there in the retina? | factual | 1.000 | 0.333 | 1.000 | 0.050 | 0.333 | 0.296 | 611, 612, 642 | 612, 622, 623 |
| gold-054 | What are the two main functions of the different kinds … | factual | 1.000 | 1.000 | 1.000 | 0.050 | 0.500 | 1.000 | 612, 611, 633 | 612 |
| gold-057 | What does the curve marked P1 in part (b) of Fig. 37-3 … | factual | 0.333 | 0.333 | 1.000 | 0.050 | 0.500 | 0.167 | 792, 810, 812 | 656, 660, 662 |
| gold-058 | How does the result P12 obtained with both holes open d… | multihop | 0.583 | 0.583 | 1.000 | 0.350 | 1.000 | 0.679 | 662, 663, 665 | 503, 504, 509, 510, 657, 658, 659, 660, … |
| gold-059 | How many spin cases allow two electrons to sit on top o… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 1.000 | 686, 662, 661 | 686 |
| gold-060 | Why does the inability of all electrons to occupy the s… | multihop | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 1.000 | 686, 685, 756 | 686 |
| gold-061 | What is the kinetic energy associated with the componen… | factual | 0.800 | 0.400 | 1.000 | 0.200 | 1.000 | 0.392 | 707, 228, 357 | 698, 705, 707, 708, 710, 711, 719, 722, … |
| gold-062 | How many independent directions contribute to the total… | multihop | 1.000 | 0.500 | 1.000 | 0.150 | 1.000 | 0.584 | 707, 730, 710 | 698, 707, 708, 709, 710, 711 |
| gold-063 | According to the passage, what is the energy of a parti… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 0.431 | 277, 796, 255 | 731 |
| gold-064 | In Figure 41-1, what component reflects light from sour… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 0.018 | 0.245 | 732, 288, 457 | 731 |
| gold-065 | What is occurring to a certain number of atoms at a giv… | multihop | 0.889 | 0.667 | 1.000 | 0.300 | 1.000 | 0.688 | 750, 751, 748 | 42, 43, 45, 749, 750, 751, 752, 753, … |
| gold-067 | What term does the passage use to refer to the majority… | factual | 0.444 | 0.222 | 1.000 | 0.100 | 0.200 | 0.135 | 772, 842, 781 | 131, 134, 694, 698, 713, 724, 728, 729, … |
| gold-068 | Why does the passage refer to molecules that differ fro… | multihop | 1.000 | 0.800 | 1.000 | 0.200 | 1.000 | 0.806 | 772, 779, 45 | 771, 772, 776, 777, 779 |
| gold-069 | What is the net result of the two machines in tandem in… | multihop | 0.889 | 0.778 | 1.000 | 0.350 | 1.000 | 0.758 | 797, 794, 799 | 791, 794, 795, 796, 797, 800, 806, 826, … |
| gold-070 | What action does the second machine perform with the he… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 1.000 | 797, 794, 806 | 797 |
| gold-071 | What temperature condition is assumed for T1 and T2 in … | factual | 0.759 | 0.414 | 1.000 | 0.600 | 1.000 | 0.714 | 789, 794, 799 | 732, 733, 739, 787, 789, 790, 791, 792, … |
| gold-072 | Why would the proposed device violate the Second Law of… | multihop | 0.385 | 0.308 | 1.000 | 0.200 | 0.333 | 0.306 | 823, 788, 786 | 88, 89, 90, 257, 739, 787, 788, 794, … |
| gold-073 | According to the passage, what type of disturbance does… | factual | 0.762 | 0.571 | 1.000 | 0.600 | 1.000 | 0.654 | 841, 849, 840 | 837, 838, 840, 841, 842, 843, 844, 845, … |
| gold-074 | Why does the passage state that for rapid motion of an … | multihop | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 1.000 | 841, 201, 184 | 841 |
| gold-075 | What does the variable c represent in the one‑dimension… | factual | 0.700 | 0.400 | 1.000 | 0.200 | 1.000 | 0.499 | 847, 864, 410 | 846, 847, 848, 864, 865, 868, 870, 871, … |
| gold-076 | According to the passage, how does the meaning of c dif… | multihop | 1.000 | 1.000 | 1.000 | 0.150 | 1.000 | 0.907 | 864, 848, 858 | 848, 864, 900 |
| gold-077 | By throwing the switches on an organ, which instrument … | factual | 1.000 | 1.000 | 1.000 | 0.100 | 1.000 | 0.770 | 887, 884, 883 | 886, 887 |
| gold-078 | According to the passage, how does the shape of the mou… | multihop | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 887, 876, 902 | 886 |
| gold-079 | According to the passage, how does the speed of long wa… | factual | 1.000 | 1.000 | 1.000 | 0.050 | 1.000 | 0.500 | 903, 912, 915 | 915 |
| gold-080 | How does the change in water depth lead to the formatio… | multihop | 1.000 | 1.000 | 1.000 | 0.050 | 0.333 | 1.000 | 915, 903, 34 | 915 |
| gold-081 | How long does it take for a falling body to reach a vel… | multihop | 0.750 | 0.500 | 1.000 | 0.100 | 1.000 | 0.586 | 172, 168, 167 | 167, 170, 172, 627 |
| gold-082 | How does the mass of a particle appear in both the quan… | multihop | 0.667 | 0.667 | 1.000 | 0.100 | 0.250 | 0.578 | 135, 349, 206 | 54, 135, 826 |
| gold-083 | How does the acceleration of the unit vector in far‑fie… | multihop | 0.667 | 0.667 | 1.000 | 0.100 | 0.250 | 0.582 | 921, 359, 489 | 30, 490, 921 |
| gold-084 | What effect does the centrifugal force in a rotating sp… | multihop | 0.333 | 0.333 | 1.000 | 0.050 | 0.333 | 0.469 | 921, 358, 375 | 30, 490, 921 |
| gold-085 | How does the compressibility of radiation influence the… | multihop | 0.667 | 0.667 | 1.000 | 0.100 | 0.500 | 0.287 | 701, 34, 305 | 30, 490, 921 |
| gold-086 | How does the requirement that velocity vectors be drawn… | multihop | 0.667 | 0.000 | 0.000 | 0.000 | 0.083 | 0.000 | 676, 667, 37 | 137, 224, 662 |
| gold-087 | Using the relationship v² = GM/a for a satellite's orbi… | multihop | 1.000 | 0.500 | 1.000 | 0.050 | 1.000 | 0.613 | 274, 251, 186 | 169, 274 |
| gold-088 | According to the product rule for differentiation, how … | multihop | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 568, 572, 571 | 169, 274 |
| gold-089 | How does the continuous range of photon energies, as de… | multihop | 0.333 | 0.000 | 0.000 | 0.000 | 0.021 | 0.000 | 766, 774, 453 | 97, 665, 765 |
| gold-090 | What is the relationship between the energy loss rate o… | multihop | 0.667 | 0.667 | 1.000 | 0.100 | 0.500 | 0.416 | 499, 734, 735 | 74, 735, 822 |
| gold-091 | How does the principle of conservation of energy in a f… | multihop | 0.667 | 0.333 | 1.000 | 0.050 | 0.143 | 0.469 | 95, 789, 385 | 95, 391, 788 |
| gold-092 | How does the phase velocity of surface tension waves re… | multihop | 0.667 | 0.667 | 1.000 | 0.100 | 1.000 | 0.765 | 914, 687, 913 | 432, 687, 914 |
| gold-093 | If cobalt atoms emit electrons downward in a magnetic f… | multihop | 0.231 | 0.231 | 1.000 | 0.150 | 1.000 | 0.385 | 932, 299, 541 | 298, 299, 300, 301, 302, 311, 312, 314, … |
| gold-094 | What does the 5‑billion‑year age of meteorites imply ab… | multihop | 0.500 | 0.500 | 1.000 | 0.050 | 1.000 | 0.613 | 108, 159, 691 | 108, 474 |
| gold-095 | How does the Heisenberg uncertainty principle impact th… | multihop | 0.333 | 0.333 | 1.000 | 0.050 | 0.125 | 0.202 | 672, 667, 671 | 219, 673, 934 |
| gold-096 | How does the concept of gravitational potential energy … | multihop | 0.667 | 0.667 | 1.000 | 0.100 | 0.083 | 0.251 | 90, 251, 275 | 83, 252, 531 |
| gold-097 | How does the energy-time uncertainty principle affect t… | multihop | 0.667 | 0.667 | 1.000 | 0.100 | 0.200 | 0.315 | 684, 698, 815 | 118, 707, 831 |
| gold-098 | How does the adiabatic expansion of a perfect gas, driv… | multihop | 0.333 | 0.333 | 1.000 | 0.050 | 0.200 | 0.469 | 116, 790, 792 | 116, 248, 791 |
| gold-099 | How might vector analysis be applied to model the flux … | multihop | 0.667 | 0.667 | 1.000 | 0.100 | 0.500 | 0.611 | 42, 749, 557 | 42, 219, 321 |
| gold-100 | How does the delay time in the radiation formula for sl… | multihop | 0.667 | 0.667 | 1.000 | 0.100 | 1.000 | 0.600 | 490, 487, 491 | 167, 490, 750 |
| gold-101 | How does changing the coordinate origin influence the a… | multihop | 0.333 | 0.333 | 1.000 | 0.050 | 1.000 | 0.469 | 438, 247, 428 | 214, 438, 649 |
| gold-102 | How does the principle that experiments yield consisten… | multihop | 0.200 | 0.200 | 1.000 | 0.100 | 1.000 | 0.276 | 592, 286, 590 | 61, 287, 293, 323, 331, 332, 398, 592, … |
| gold-103 | How does the necessity of continuity and ordering in de… | multihop | 0.667 | 0.667 | 1.000 | 0.100 | 1.000 | 0.704 | 62, 488, 393 | 62, 264, 393 |
| ovw-001 | In what ways does Feynman use the principle of conserva… | overview | 0.287 | 0.113 | 1.000 | 0.650 | 1.000 | 0.671 | 277, 278, 272 | 31, 40, 43, 46, 85, 86, 87, 88, … |
| ovw-002 | How does Feynman develop the principle of conservation … | overview | 0.471 | 0.275 | 1.000 | 0.700 | 1.000 | 0.735 | 198, 199, 211 | 90, 178, 197, 198, 199, 200, 201, 202, … |
| ovw-003 | How does Feynman develop the concept of conservation of… | overview | 0.909 | 0.409 | 1.000 | 0.450 | 1.000 | 0.430 | 97, 369, 921 | 149, 338, 340, 341, 342, 343, 344, 345, … |
| ovw-004 | How does the Feynman Lectures on Physics, Volume 1, tra… | overview | 0.318 | 0.082 | 1.000 | 0.350 | 0.500 | 0.399 | 97, 921, 922 | 33, 86, 90, 97, 98, 135, 197, 198, … |
| ovw-005 | How does Feynman develop the concept of wave‑particle d… | overview | 0.477 | 0.204 | 1.000 | 0.450 | 0.250 | 0.420 | 562, 34, 666 | 30, 61, 118, 332, 467, 468, 469, 517, … |
| ovw-006 | How does Feynman build up the concept of quantum probab… | overview | 0.522 | 0.239 | 1.000 | 0.550 | 1.000 | 0.610 | 668, 662, 744 | 30, 404, 468, 469, 495, 509, 510, 511, … |
| ovw-007 | How does the Feynman Lectures on Physics, Volume 1 deve… | overview | 0.592 | 0.347 | 1.000 | 0.850 | 0.500 | 0.892 | 296, 308, 292 | 209, 227, 286, 287, 288, 290, 291, 292, … |
| ovw-008 | How does Feynman develop the concept of mass-energy equ… | overview | 0.636 | 0.333 | 1.000 | 0.550 | 1.000 | 0.572 | 302, 296, 96 | 35, 96, 97, 209, 284, 286, 287, 290, … |
| ovw-009 | How does Feynman develop the kinetic theory of gases th… | overview | 0.299 | 0.095 | 1.000 | 0.600 | 1.000 | 0.604 | 694, 34, 782 | 31, 36, 37, 38, 39, 40, 43, 49, … |
| ovw-010 | In what way does Feynman build the concept of entropy f… | overview | 0.472 | 0.333 | 1.000 | 0.600 | 1.000 | 0.710 | 805, 834, 831 | 31, 32, 43, 89, 120, 702, 704, 705, … |
| ovw-011 | How does Feynman develop the concept of electromagnetic… | overview | 0.344 | 0.107 | 1.000 | 0.700 | 1.000 | 0.734 | 848, 53, 486 | 57, 209, 210, 242, 245, 246, 287, 290, … |
| ovw-012 | How does Feynman develop the concept of Fermat's princi… | overview | 0.518 | 0.148 | 1.000 | 0.200 | 1.000 | 0.277 | 457, 588, 848 | 290, 456, 457, 458, 459, 460, 462, 463, … |
| ovw-013 | How does Feynman develop the concept of oscillatory mot… | overview | 0.338 | 0.115 | 1.000 | 0.900 | 1.000 | 0.922 | 260, 436, 867 | 57, 85, 86, 87, 91, 94, 95, 102, … |
| ovw-014 | How does Feynman develop the concept of the harmonic os… | overview | 0.569 | 0.155 | 1.000 | 0.450 | 1.000 | 0.473 | 740, 761, 687 | 183, 184, 187, 260, 378, 379, 380, 381, … |
| ovw-015 | How does Feynman build the statistical mechanical frame… | overview | 0.268 | 0.122 | 1.000 | 0.500 | 0.333 | 0.460 | 34, 722, 808 | 31, 39, 40, 43, 86, 120, 131, 133, … |
| ovw-016 | How does Feynman develop the concept of chemical energy… | overview | 0.419 | 0.163 | 1.000 | 0.350 | 0.500 | 0.394 | 277, 723, 815 | 38, 40, 43, 46, 74, 86, 275, 277, … |
| ovw-017 | How does Feynman build the concept of atomic forces thr… | overview | 0.310 | 0.090 | 1.000 | 0.700 | 1.000 | 0.725 | 53, 276, 654 | 30, 31, 40, 49, 53, 55, 56, 57, … |
| ovw-019 | In what ways does Feynman's discussion of the uncertain… | overview | 0.710 | 0.355 | 1.000 | 0.550 | 1.000 | 0.589 | 690, 727, 668 | 30, 35, 59, 60, 118, 135, 136, 137, … |
| ovw-020 | How does Feynman's exposition of electron interference … | overview | 0.667 | 0.333 | 1.000 | 0.550 | 1.000 | 0.632 | 660, 668, 667 | 30, 60, 118, 120, 137, 138, 468, 469, … |
| ovw-024 | How does Feynman develop the concept of rotational dyna… | overview | 0.667 | 0.250 | 1.000 | 0.450 | 1.000 | 0.437 | 97, 344, 830 | 146, 216, 333, 338, 339, 340, 341, 342, … |
| ovw-027 | How does Feynman develop the concept of diffusion from … | overview | 0.400 | 0.143 | 1.000 | 0.250 | 1.000 | 0.323 | 133, 34, 819 | 31, 37, 127, 128, 131, 132, 133, 661, … |
| ovw-029 | How does Feynman's treatment of color vision evolve thr… | overview | 0.765 | 0.412 | 1.000 | 0.700 | 1.000 | 0.655 | 653, 610, 628 | 610, 612, 613, 614, 615, 616, 617, 618, … |
| ovw-030 | How does Feynman integrate the concepts of sound wave p… | overview | 0.493 | 0.151 | 1.000 | 0.550 | 1.000 | 0.573 | 842, 840, 858 | 32, 86, 378, 387, 388, 406, 409, 412, … |
| ovw-031 | How does Feynman develop the concept of Fourier analysi… | overview | 0.197 | 0.118 | 1.000 | 0.450 | 0.500 | 0.537 | 892, 870, 875 | 32, 387, 388, 401, 403, 404, 406, 407, … |
| ovw-034 | How does The Feynman Lectures on Physics, Volume 1, bui… | overview | 0.640 | 0.360 | 1.000 | 0.450 | 1.000 | 0.507 | 118, 671, 820 | 30, 118, 332, 608, 609, 661, 666, 667, … |
| ovw-035 | How does Feynman build the concept of probability as a … | overview | 0.424 | 0.273 | 1.000 | 0.450 | 0.500 | 0.504 | 834, 920, 831 | 32, 43, 120, 656, 661, 702, 704, 705, … |
| ovw-036 | How does Feynman develop the concept of thermodynamic t… | overview | 0.414 | 0.129 | 1.000 | 0.450 | 1.000 | 0.577 | 796, 707, 799 | 31, 39, 40, 88, 89, 90, 96, 695, … |
| ovw-037 | How does Feynman develop the concept of boundary condit… | overview | 0.223 | 0.064 | 1.000 | 0.300 | 1.000 | 0.301 | 87, 877, 876 | 57, 210, 290, 382, 385, 419, 457, 459, … |
| ovw-038 | How does Feynman develop the concept of potential energ… | overview | 0.552 | 0.239 | 1.000 | 0.800 | 1.000 | 0.822 | 277, 255, 275 | 56, 57, 86, 87, 88, 89, 90, 91, … |
| ovw-039 | How does The Feynman Lectures on Physics, Volume 1 deve… | overview | 0.327 | 0.125 | 1.000 | 0.650 | 1.000 | 0.608 | 687, 663, 662 | 30, 210, 404, 419, 437, 439, 440, 442, … |
| ovw-040 | How does Feynman's presentation in Volume 1 illustrate … | overview | 0.446 | 0.174 | 1.000 | 0.800 | 1.000 | 0.845 | 654, 59, 687 | 30, 31, 35, 50, 53, 54, 59, 60, … |
| ovw-041 | How does Feynman develop the concept and applications o… | overview | 0.630 | 0.391 | 1.000 | 0.900 | 1.000 | 0.913 | 348, 354, 336 | 142, 146, 177, 178, 200, 201, 203, 333, … |
| ovw-042 | How does Feynman develop a unified understanding of wav… | overview | 0.340 | 0.170 | 1.000 | 0.850 | 1.000 | 0.881 | 846, 864, 848 | 32, 57, 210, 286, 378, 415, 416, 419, … |
| ovw-043 | How does Feynman develop the concept of transformation … | overview | 0.277 | 0.135 | 1.000 | 0.800 | 1.000 | 0.723 | 97, 705, 922 | 85, 86, 89, 90, 165, 197, 198, 199, … |
| ovw-044 | How does Feynman develop the concept of time–distance r… | overview | 0.153 | 0.045 | 1.000 | 0.700 | 1.000 | 0.678 | 920, 252, 173 | 40, 57, 86, 89, 90, 91, 94, 95, … |
| ovw-045 | How does Feynman build a coherent narrative of thermal … | overview | 0.473 | 0.164 | 1.000 | 0.450 | 1.000 | 0.517 | 787, 760, 823 | 31, 490, 530, 550, 557, 567, 692, 696, … |
| ovw-046 | How does Feynman's presentation of molecular kinetic be… | overview | 0.333 | 0.114 | 1.000 | 0.650 | 1.000 | 0.564 | 717, 815, 34 | 31, 36, 37, 38, 39, 40, 42, 43, … |
| ovw-047 | How does Feynman's treatment of the interaction of ligh… | overview | 0.337 | 0.137 | 1.000 | 0.650 | 1.000 | 0.646 | 453, 588, 62 | 30, 57, 59, 60, 61, 62, 137, 210, … |
| ovw-048 | How does Feynman develop the concept of atomic and mole… | overview | 0.708 | 0.458 | 1.000 | 0.550 | 0.500 | 0.528 | 761, 881, 33 | 30, 60, 79, 137, 544, 547, 682, 684, … |
| ovw-049 | How does Feynman build the theory of quantum state evol… | overview | 0.435 | 0.174 | 1.000 | 0.200 | 0.333 | 0.304 | 675, 663, 134 | 30, 468, 469, 563, 567, 656, 659, 660, … |
| neg-out-001 | What is the capital of France? | factual | — | — | — | — | — | — | 322, 108, 213 | — |
| neg-out-002 | Who wrote Pride and Prejudice? | factual | — | — | — | — | — | — | 175, 558, 79 | — |
| neg-out-003 | What is the boiling point of mercury in Fahrenheit? | factual | — | — | — | — | — | — | 816, 818, 817 | — |
| neg-out-004 | What are the rules of cricket? | factual | — | — | — | — | — | — | 750, 167, 122 | — |
| neg-out-005 | How do you bake sourdough bread? | factual | — | — | — | — | — | — | 699, 842, 357 | — |
| neg-out-006 | What is the population of Tokyo? | factual | — | — | — | — | — | — | 120, 139, 114 | — |
| neg-out-007 | Which company makes the iPhone? | factual | — | — | — | — | — | — | 397, 924, 926 | — |
| neg-out-008 | What language is spoken in Brazil? | factual | — | — | — | — | — | — | 378, 87, 85 | — |
| neg-out-009 | What is the tallest mountain in the world? | factual | — | — | — | — | — | — | 145, 646, 904 | — |
| neg-out-010 | Who painted the Mona Lisa? | factual | — | — | — | — | — | — | 632, 139, 901 | — |
| neg-out-011 | How do you change a car tyre? | factual | — | — | — | — | — | — | 375, 161, 371 | — |
| neg-out-012 | What is the capital of Australia? | factual | — | — | — | — | — | — | 378, 85, 805 | — |
| neg-in_-001 | What does the book say about the Schrödinger equation f… | factual | — | — | — | — | — | — | 136, 550, 685 | — |
| neg-in_-002 | What is the book's treatment of general relativity and … | factual | — | — | — | — | — | — | 307, 322, 285 | — |
| neg-in_-003 | What does the book say about the Higgs boson and electr… | factual | — | — | — | — | — | — | 705, 655, 727 | — |
| neg-in_-004 | What is the book's explanation of quantum entanglement … | factual | — | — | — | — | — | — | 67, 930, 53 | — |
| neg-in_-005 | What does the book say about the Standard Model of part… | factual | — | — | — | — | — | — | 66, 198, 62 | — |
| neg-in_-006 | What is the book's derivation of the Navier-Stokes equa… | factual | — | — | — | — | — | — | 601, 211, 859 | — |
| neg-in_-007 | What does the book say about superconductivity and the … | factual | — | — | — | — | — | — | 594, 662, 863 | — |
| neg-in_-008 | What is the book's treatment of the Fourier transform i… | factual | — | — | — | — | — | — | 34, 892, 558 | — |
| neg-in_-009 | What does the book say about the quantum Hall effect? | factual | — | — | — | — | — | — | 660, 662, 655 | — |
| neg-in_-010 | What is the book's treatment of the strong nuclear forc… | factual | — | — | — | — | — | — | 249, 67, 239 | — |
| neg-in_-011 | What does the book say about gravitational waves? | factual | — | — | — | — | — | — | 243, 59, 153 | — |
| neg-in_-012 | What is the book's explanation of black hole thermodyna… | factual | — | — | — | — | — | — | 787, 806, 694 | — |
| neg-nea-001 | What numerical value does the book give for the electro… | factual | — | — | — | — | — | — | 595, 593, 754 | — |
| neg-nea-002 | What does the book say the mass of the top quark is? | factual | — | — | — | — | — | — | 198, 154, 314 | — |
| neg-nea-003 | Which year does the book state that the laser was inven… | factual | — | — | — | — | — | — | 632, 562, 653 | — |
| neg-nea-005 | What value does the book use for the cosmological const… | factual | — | — | — | — | — | — | 499, 157, 284 | — |
| neg-nea-006 | What does the book say the speed of sound in seawater i… | factual | — | — | — | — | — | — | 849, 901, 913 | — |
| neg-nea-007 | What does the book list as the melting point of tungste… | factual | — | — | — | — | — | — | 395, 169, 819 | — |
| neg-nea-008 | How many moons does the book say Jupiter has? | factual | — | — | — | — | — | — | 147, 143, 109 | — |
| neg-nea-009 | What value does the book give for the mass of the proto… | factual | — | — | — | — | — | — | 64, 558, 317 | — |
| neg-nea-011 | What does the book give as the boiling point of liquid … | factual | — | — | — | — | — | — | 804, 42, 34 | — |
| neg-nea-012 | Which year does the book give for the discovery of the … | factual | — | — | — | — | — | — | 250, 761, 731 | — |

## Config

- **Tenant:** global
- **Collection:** knowledge_base_v2
- **Embedder:** nomic-ai/nomic-embed-text-v1.5
- **SPLADE:** True
- **Reranker:** True (BAAI/bge-reranker-v2-m3)
- **Min content page:** 30
- **Score threshold:** 0.0
- **Judge:** none
- **Elapsed:** 647.7s

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
    "dim": 1024,
    "model": "Qwen/Qwen3-Embedding-0.6B"
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
    "collection": "knowledge_base_v2",
    "fetch_k": 100,
    "splade_enabled": true,
    "type": "hybrid (SPLADE+dense RRF)"
  },
  "score_threshold": 0.0,
  "tenant_id": "global"
}
```

</details>
