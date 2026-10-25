# P1 — RE-REGISTRATION ADDENDUM: the MRL convention A/B, guard G4 restated

> **Written 2026-10-25 (session 18), BEFORE the re-run.** Supersedes **only** guard **G4** of
> `.hermes/plans/2026-10-25-p1-mrl-convention-ab-preregistration.md`. Everything else — the arms, the
> primary endpoint, the decision rule, G1/G2/G3/G5/G6 — stands unchanged. The pre-registration itself
> is **NOT edited** (that is what makes it a pre-registration).

## What happened

The first run completed and every guard passed **except G4** (exit 1). The primary endpoint was a
clean null: paired ceiling-normalised R@20, arm B − arm A = **+0.000314**, CI [−0.003539, +0.004167],
**unresolved**, W/L/T 1/2/130, against the run's own resolution floor **0.003853**. G1 and G2
reproduced §I70's registered `nomic@64` rows **exactly**, which pins the instrument.

## Why G4 failed — and why it is the GUARD that was wrong, not the run

G4's non-vacuity clause required `cos(arm A, arm B) < 0.999`, so that the contrast could not be a
function compared against itself. **The threshold was calibrated on the wrong input.** The
pre-registration quotes `cos = 0.2616` from a *synthetic* 768d probe drawn uniformly from `[3, 13]`
and then unit-normed — an **all-positive vector with a large DC component**, so subtracting the mean
(which is what `layer_norm` does) changes its direction enormously.

On the **real** nomic embeddings the measured value is **`cos(A, B) = 0.999987`**, and the reason is
arithmetic: for a unit-norm vector of width *n*, the mean component is ~`σ/√n`, so removing it moves
the direction by ~`1/√768 ≈ 0.036` of the vector's scale — a cosine change of order `1e-5`. The two
conventions are genuinely different *functions* (and produce genuinely different vectors, row for
row), but on this data they are nearly the same *direction*, which is itself the explanation for the
+0.0003 null. **The guard asserted a property of the data, not of the code.**

## G4′ — the restated guard

G4′ asserts what the guard is actually for, and adds an independent implementation check:

| id | assertion | why |
|---|---|---|
| **G4a** | the harness's numpy `layer_norm` equals **torch's `F.layer_norm`** on a 32-row sample (max abs diff < 1e-9) | the arm-B *implementation* is verified against a second library, not against itself |
| **G4b** | arm B equals the slice + re-normalise **of that torch layer-norm** (max abs diff < 1e-9) | pins the whole arm-B chain to torch |
| **G4c** | both arms are unit-norm, and arm A is the **exact** truncation of the full vector | unchanged from G4 |
| **G4d** | the two arms are **not bit-identical** (`any(A != B)`), with `n_rows_differing` and `mean_cos_A_vs_B` **reported as findings** | the contrast is real; the *size* of the difference is a result, not a gate |

⚠️ **This is a disambiguation of the original wording, not a relaxation to get past a red guard** —
the §I67 `E4→E4′` precedent. The direction matters: G4d is *stricter* about what it demands (a real
bit-level difference) and *silent* about a magnitude the data turned out not to have.

## Disposition

* The **first-run artifact is preserved** as `logs/p1/step10/mrl_convention_ab_firstrun.json` — its
  numbers are **not** void (G1/G2/G3/G5/G6 passed and the endpoint is valid); only its guard set was
  mis-specified.
* The **re-run** writes `logs/p1/step10/mrl_convention_ab.json` with G4′. The **conclusion is
  expected to be identical** (keep the project's plain slice) and is **not** to be switched after
  seeing numbers.
