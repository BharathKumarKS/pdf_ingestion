#!/usr/bin/env python3
"""
Create a multi-page sample physics PDF for testing the ingestion pipeline.

Usage:
    uv run python scripts/create_test_pdf.py
    writes -> tests/data/sample_physics.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


CHAPTERS = [
    (
        "Chapter 1: Mechanics and Motion",
        (
            "Newton's Laws of Motion form the cornerstone of classical mechanics. "
            "The first law, often called the law of inertia, states that an object at rest "
            "remains at rest, and an object in motion remains in motion with the same speed "
            "and in the same direction unless acted upon by an unbalanced force.\n\n"
            "The second law establishes that the net force acting on an object equals the mass "
            "of the object multiplied by its acceleration: F = m*a. This relationship is one "
            "of the most fundamental equations in all of physics. When the net force on an "
            "object is zero, the object is said to be in a state of equilibrium.\n\n"
            "The third law states that for every action there is an equal and opposite reaction. "
            "When object A exerts a force on object B, object B simultaneously exerts a force "
            "on object A that is equal in magnitude and opposite in direction.\n\n"
            "Kinematics describes motion without considering its causes. The key equations for "
            "uniformly accelerated motion are: v = u + at, s = u*t + (1/2)*a*t^2, "
            "v^2 = u^2 + 2*a*s, where u is initial velocity, v is final velocity, "
            "a is acceleration, t is time, and s is displacement."
        ),
    ),
    (
        "Chapter 2: Energy, Work, and Power",
        (
            "Work is done when a force causes displacement. The work done by a constant force F "
            "over displacement d is: W = F * d * cos(angle), where angle is between the force "
            "and displacement vectors. Work is measured in joules (J).\n\n"
            "Kinetic energy is the energy possessed by an object due to its motion: "
            "KE = (1/2) * m * v^2\n\n"
            "Potential energy is the energy stored in an object due to its position. "
            "For gravitational potential energy near Earth's surface: PE = m * g * h\n\n"
            "The work-energy theorem states that the net work done on an object equals its "
            "change in kinetic energy: W_net = delta(KE).\n\n"
            "Conservation of energy is one of the most fundamental principles in physics. "
            "In an isolated system, the total mechanical energy (KE + PE) remains constant "
            "when only conservative forces act.\n\n"
            "Power is the rate at which work is done: P = W/t = F*v. "
            "Power is measured in watts (W), where 1 W = 1 J/s."
        ),
    ),
    (
        "Chapter 3: Waves and Oscillations",
        (
            "Simple Harmonic Motion (SHM) is a type of periodic motion where the restoring "
            "force is directly proportional to the displacement and acts in the direction "
            "opposite to the displacement: F = -k*x, where k is the spring constant.\n\n"
            "The period of SHM is: T = 2*pi*sqrt(m/k). "
            "The frequency is: f = 1/T = (1/(2*pi))*sqrt(k/m).\n\n"
            "A wave is a disturbance that transfers energy through matter or space without "
            "transferring matter. Transverse waves oscillate perpendicular to the direction "
            "of propagation (e.g., light, electromagnetic waves). Longitudinal waves oscillate "
            "parallel to the direction of propagation (e.g., sound waves).\n\n"
            "The wave equation relates wave speed, frequency, and wavelength: v = f * lambda.\n\n"
            "The Doppler Effect describes the change in observed frequency when the source "
            "and observer are moving relative to each other. When they approach, the observed "
            "frequency is higher; when they recede, it is lower.\n\n"
            "Sound intensity is measured in decibels (dB). The threshold of human hearing "
            "is approximately 10^(-12) W/m^2."
        ),
    ),
    (
        "Chapter 4: Electromagnetism",
        (
            "Coulomb's Law describes the force between two point charges: "
            "F = k * q1 * q2 / r^2, where k = 8.99e9 N*m^2/C^2, q1 and q2 are the charges, "
            "and r is the distance between them.\n\n"
            "The electric field E at a point in space is defined as the force per unit charge: "
            "E = F/q.\n\n"
            "Gauss's Law relates the electric flux through a closed surface to the total "
            "charge enclosed: Phi = Q_enclosed / epsilon_0.\n\n"
            "Faraday's Law of electromagnetic induction states that a changing magnetic "
            "flux through a circuit induces an EMF: EMF = -d(Phi_B)/dt.\n\n"
            "Maxwell's equations unify electricity and magnetism into a single framework "
            "and predict the existence of electromagnetic waves travelling at the speed "
            "of light: c = 1/sqrt(epsilon_0 * mu_0) which is approximately 3e8 m/s.\n\n"
            "The electromagnetic spectrum includes radio waves, microwaves, infrared, "
            "visible light, ultraviolet, X-rays, and gamma rays -- all travelling at the "
            "speed of light but differing in frequency and wavelength."
        ),
    ),
    (
        "Chapter 5: Modern Physics",
        (
            "Quantum mechanics describes physics at the atomic and subatomic scale. "
            "The photoelectric effect demonstrated that light behaves as discrete packets "
            "of energy called photons: E = h * f, where h = 6.626e-34 J*s is Planck's constant.\n\n"
            "De Broglie proposed that matter also has wave-like properties. The de Broglie "
            "wavelength of a particle with momentum p is: lambda = h / p.\n\n"
            "The Heisenberg Uncertainty Principle states that there is a fundamental limit "
            "to the precision with which certain pairs of physical properties can be known "
            "simultaneously: delta_x * delta_p >= hbar / 2.\n\n"
            "The Schrodinger equation describes how quantum states evolve over time. "
            "Its solutions, called wave functions psi, encode the probability distribution "
            "of finding a particle at a given location.\n\n"
            "Einstein's Special Theory of Relativity established that the laws of physics "
            "are the same in all inertial reference frames, and that the speed of light is "
            "constant for all observers. Key consequences include time dilation and "
            "length contraction.\n\n"
            "Mass-energy equivalence: E = m * c^2 shows that mass and energy are "
            "interchangeable. Nuclear fission and fusion processes release enormous amounts "
            "of energy through this principle."
        ),
    ),
]


def create_test_pdf(output_path: str = "tests/data/sample_physics.pdf") -> str:
    from fpdf import FPDF, XPos, YPos

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Cover page
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 24)
    pdf.cell(0, 20, "Fundamentals of Physics",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.set_font("Helvetica", "", 14)
    pdf.cell(0, 10, "A Comprehensive Introduction",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 11)
    pdf.cell(0, 8,
             "Sample textbook for Synapse Learning Worlds pipeline testing",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align="C")

    # Chapter pages
    for title, body in CHAPTERS:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 12, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(4)
        pdf.set_font("Helvetica", "", 11)
        pdf.multi_cell(0, 6, body.strip())

    pdf.output(str(out))
    size_kb = out.stat().st_size / 1024
    pages = len(CHAPTERS) + 1
    print(f"Created test PDF: {out}  ({size_kb:.1f} KB, {pages} pages)")
    return str(out)


if __name__ == "__main__":
    create_test_pdf()
