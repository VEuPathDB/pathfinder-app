"""A request whose requirements are joined by commas and each hold an inner "or"."""

from __future__ import annotations

VACCINE = (
    "Find Plasmodium falciparum 3D7 genes that are candidate blood-stage vaccine "
    "antigens: expressed in late schizonts or merozoites, with a signal peptide "
    "or GPI anchor, no transmembrane domains beyond a signal anchor, and evidence "
    "of expression in proteomics data."
)
VACCINE_TERMS = [
    "expressed in late schizonts or merozoites",
    "with a signal peptide or GPI anchor",
    "no transmembrane domains beyond a signal anchor",
    "evidence of expression in proteomics data",
]
