"""A set whose largest species tie is said to have no one leading species."""

from __future__ import annotations

from datetime import date

from pydantic import TypeAdapter
from veupathdb_mcp.catalog import PhyleticPattern
from veupathdb_mcp.wdk import ComputedSet, SpeciesGenomes

from pathfinder.tests._support.computed_comparison import held_comparison

_PATTERN: PhyleticPattern = TypeAdapter(PhyleticPattern).validate_python(
    {
        "kind": "compare",
        "left": {"kind": "codes", "codes": ["TOXO"]},
        "right": {"kind": "codes", "codes": ["PLAS"]},
        "reading": "averages",
        "condition": "more_than",
    }
)


def test_two_species_tied_for_the_most_genomes_lead_together() -> None:
    held = held_comparison(_PATTERN, date(2026, 10, 25))
    left, _ = held.answer.sets
    tied = ComputedSet(
        side="right",
        genomes=5,
        species=(
            SpeciesGenomes(species="Plasmodium falciparum", genomes=2),
            SpeciesGenomes(species="Plasmodium vivax", genomes=2),
            SpeciesGenomes(species="Plasmodium knowlesi", genomes=1),
        ),
        groups=2,
        proteins=4,
    )
    fact = held.model_copy(
        update={"answer": held.answer.model_copy(update={"sets": (left, tied)})}
    ).fact()

    assert (fact.value("right.leadingSpecies"), fact.statements[-1]) == (
        "Plasmodium falciparum and Plasmodium vivax",
        (
            "Plasmodium falciparum and Plasmodium vivax each hold 2 of the 5 genomes "
            "of the right set (40%), the most of its 3 species; no one species "
            "leads it."
        ),
    )
