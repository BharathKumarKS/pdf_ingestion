"""Generate concept images for the visual-lane validation.

IN-DOMAIN  : concepts Feynman Vol 1 explains (waves, interference, diffraction, blackbody, oscillator,
             resonance, pendulum, energy conservation).
NEAR-DOMAIN: physics-LOOKING but NOT Vol 1 (atomic orbital / quantum, EM wave / Maxwell, a molecule,
             a financial line chart). These are the adversarial aperture test.
FAR-DOMAIN : synthetic noise + gradient (trivial controls; the logos are existing files).

Writes PNGs to logs/p1/step10/concept_images/.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy.special import j1 as _bessel_j1  # noqa: E402
from PIL import Image  # noqa: E402

OUT = Path("logs/p1/step10/concept_images")
OUT.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(7)


def _save(fig, name):
    p = OUT / f"{name}.png"
    fig.savefig(p, dpi=110, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print("wrote", p)


# ── IN-DOMAIN (Vol 1) ─────────────────────────────────────────────────────
x = np.linspace(0, 4 * np.pi, 600)

fig, ax = plt.subplots(figsize=(5, 3.4))
ax.plot(x, np.sin(x), "b-", lw=2)
ax.set_title("A sinusoidal wave"); ax.set_xlabel("distance x"); ax.set_ylabel("displacement y")
ax.grid(alpha=.3); _save(fig, "in_sine_wave")

fig, ax = plt.subplots(figsize=(5, 3.4))
th = np.linspace(-0.02, 0.02, 800)
I = (np.cos(np.pi * th * 1e3 * 5) ** 2) * (np.sinc(th * 1e3 * 12) ** 2)
ax.plot(th * 1e3, I, "k-"); ax.set_title("Two-slit interference fringes")
ax.set_xlabel("angle (mrad)"); ax.set_ylabel("intensity"); _save(fig, "in_two_slit")

fig, ax = plt.subplots(figsize=(5, 3.4))
r = np.linspace(-8, 8, 700)
airy = (2 * _bessel_j1(np.abs(r)) / np.where(r == 0, 1e-9, np.abs(r))) ** 2
ax.plot(r, airy, "k-"); ax.set_title("Diffraction by a circular aperture")
ax.set_xlabel("radius"); ax.set_ylabel("intensity"); _save(fig, "in_diffraction_airy")

fig, ax = plt.subplots(figsize=(5, 3.4))
lam = np.linspace(1e-7, 3e-6, 600)
for T, c in ((3000, "r"), (5000, "g"), (7000, "b")):
    B = (1 / lam**5) / (np.exp(1.438e-2 / (lam * T)) - 1)
    ax.plot(lam * 1e9, B / B.max(), color=c, label=f"T={T} K")
ax.set_title("Blackbody radiation spectrum"); ax.set_xlabel("wavelength (nm)")
ax.set_ylabel("relative intensity"); ax.legend(fontsize=7); _save(fig, "in_blackbody")

fig, ax = plt.subplots(figsize=(5, 3.4))
ax.plot([0, 1], [1.6, 1.6], "k-", lw=1)
ax.plot([0.5, 0.5], [1.6, 0.9], "k-", lw=1)
ax.plot([0.5, 0.5], [1.6, 0.9], "k-")
ax.plot([0.5, 0.5], [0.9, 0.2], "k-", lw=1)
ax.plot([0.5], [0.2], "ko", ms=14)
th = np.linspace(-0.5, 0.5, 50)
ax.plot(0.5 + 0.7 * np.sin(th), 0.9 - 0.7 * np.cos(th), "k--", lw=0.8)
ax.annotate("L", (0.5, 1.25)); ax.annotate("m", (0.55, 0.2))
ax.set_xlim(0, 1.4); ax.set_ylim(0, 1.8); ax.axis("off")
ax.set_title("A simple pendulum"); _save(fig, "in_pendulum")

fig, ax = plt.subplots(figsize=(5, 3.4))
w = np.linspace(0.2, 3, 600)
ax.plot(w, 1 / np.sqrt((1 - w**2) ** 2 + (w / 8) ** 2), "b-")
ax.set_title("Resonance: amplitude vs driving frequency")
ax.set_xlabel("frequency ratio"); ax.set_ylabel("amplitude"); _save(fig, "in_resonance")

fig, ax = plt.subplots(figsize=(5, 3.4))
t = np.linspace(0, 4 * np.pi, 600)
ax.plot(t, np.cos(t), "b-", label="kinetic")
ax.plot(t, np.sin(t) ** 2, "r-", label="potential")
ax.set_title("Energy exchange in a harmonic oscillator")
ax.set_xlabel("time"); ax.set_ylabel("energy"); ax.legend(fontsize=7); _save(fig, "in_oscillator")

fig, ax = plt.subplots(figsize=(5, 3.4))
h = np.linspace(0, 10, 200)
ax.plot(h, h, "r-", label="potential mgh")
ax.plot(h, 10 - h, "b-", label="kinetic")
ax.set_title("Conservation of energy on a frictionless ramp")
ax.set_xlabel("height"); ax.set_ylabel("energy"); ax.legend(fontsize=7); _save(fig, "in_energy_ramp")

# ── NEAR-DOMAIN (physics-looking, NOT Vol 1) ──────────────────────────────
xx, yy = np.meshgrid(np.linspace(-4, 4, 300), np.linspace(-4, 4, 300))
r2 = xx**2 + yy**2
orb = (r2) * np.exp(-r2)          # a radial probability density (2p-like)
fig, ax = plt.subplots(figsize=(4, 4))
ax.imshow(orb, cmap="inferno"); ax.axis("off")
ax.set_title("Hydrogen 2p orbital |psi|^2 (quantum mechanics)")
_save(fig, "near_orbital")

fig, ax = plt.subplots(figsize=(5, 3.4))
z = np.linspace(0, 4 * np.pi, 600)
ax.plot(z, np.sin(z), "r-", label="E field")
ax.plot(z, np.cos(z), "b-", label="B field")
ax.set_title("Electromagnetic wave: E and B perpendicular")
ax.set_xlabel("propagation z"); ax.set_ylabel("field"); ax.legend(fontsize=7)
_save(fig, "near_em_wave")

fig, ax = plt.subplots(figsize=(4.5, 3.6))
ang = np.linspace(0, 2 * np.pi, 7)
ax.plot(np.cos(ang), np.sin(ang), "k-")
ax.plot(0.5 * np.cos(ang), 0.5 * np.sin(ang), "k-")
for a in ang[:-1]:
    ax.plot([0.5 * np.cos(a), np.cos(a)], [0.5 * np.sin(a), np.sin(a)], "k-")
ax.set_aspect("equal"); ax.axis("off")
ax.set_title("Benzene ring: a molecular structure (chemistry)")
_save(fig, "near_molecule")

fig, ax = plt.subplots(figsize=(5, 3.4))
steps = rng.normal(0, 1, 400).cumsum()
ax.plot(steps, "k-")
ax.set_title("A financial price series (not physics)")
ax.set_xlabel("time"); ax.set_ylabel("price"); _save(fig, "near_stock_chart")

# ── FAR-DOMAIN controls ───────────────────────────────────────────────────
Image.fromarray(rng.integers(0, 255, (556, 417, 3), dtype=np.uint8)).save(OUT / "far_noise.png")
g = np.tile(np.linspace(0, 255, 417, dtype=np.uint8), (556, 1))
Image.fromarray(np.stack([g, g, g], -1)).save(OUT / "far_gradient.png")
print("wrote far_noise.png, far_gradient.png")
print("\ncounts:", len(list(OUT.glob("in_*.png"))), "in-domain,",
      len(list(OUT.glob("near_*.png"))), "near-domain,",
      len(list(OUT.glob("far_*.png"))), "far-domain")
