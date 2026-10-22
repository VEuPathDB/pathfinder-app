"""A presence over every one of three or more genomes is found in an expression,
unless the expression also counts that list's proteins."""

from __future__ import annotations

import math

import pytest
from veupathdb.domain.parameters import PhyleticExpression

from pathfinder.domain.strategy.every_genome import (
    every_genome_units,
    names_genomes,
    presence_readings,
)
from pathfinder.tests._support.ortho_taxonomy import (
    labelled_genomes,
    recorded_ortho_taxonomy,
)

TREE = recorded_ortho_taxonomy()
PLAS = "+".join(labelled_genomes(TREE, "Plasmodium "))
TOXO = "+".join(labelled_genomes(TREE, "Toxoplasma "))
APIC = "+".join(sorted(TREE.genomes_under(["APIC"])))
_ONE_PER_SPECIES = "+".join(
    group.genomes[0] for group in TREE.species_groups(["APIC"])[:10]
)


def _units(text: str) -> list[str]:
    return [
        unit.render()
        for unit in every_genome_units(PhyleticExpression.parse(text), TREE)
    ]


def test_single_copy_binds_as_written() -> None:
    assert _units("APIC=139T AND APIC=139") == []
    assert _units(f"APIC=139T AND {APIC}=139") == []


def test_presence_in_every_genome_of_a_clade_is_found() -> None:
    assert _units("APIC=139T") == ["APIC=139T"]


def test_presence_in_every_genome_of_a_list_is_found() -> None:
    assert _units(f"{PLAS}=61T AND {TOXO}=0T") == [f"{PLAS}=61T"]
    assert _units(f"{PLAS}>=61T") == [f"{PLAS}>=61T"]


def test_three_genomes_are_many_and_two_are_few() -> None:
    assert _units("pfal+pfag+pfhb=3T") == ["pfal+pfag+pfhb=3T"]
    assert _units("pfal+pfag=2T") == []


def test_a_protein_count_at_the_genome_count_is_not_presence() -> None:
    assert _units("pfal+pfag+pfhb=3") == []


def test_genomes_of_single_genome_species_under_ten_offer_no_other_reading() -> None:
    assert _units("pfal+pviv+tgon=3T") == []
    assert _units("pfal+tgon+cpar+ncan+eten=5T AND hsap=0T") == []


def test_only_the_readings_that_differ_from_every_genome_are_offered() -> None:
    def read(text: str) -> tuple[bool, bool]:
        readings = presence_readings(
            every_genome_units(PhyleticExpression.parse(text), TREE), TREE
        )
        return readings.share_differs, readings.species_differ

    assert read("pfal+pfag+pfhb=3T") == (False, True)
    assert read(f"{PLAS}=61T") == (True, True)
    assert read(f"{TOXO}=15T") == (True, True)
    assert read(f"{_ONE_PER_SPECIES}=10T") == (True, False)


def test_a_share_or_a_species_reading_is_not_every_genome() -> None:
    every_species = " AND ".join(
        f"{'+'.join(group.genomes)}>={math.ceil(len(group.genomes) / 2)}T"
        for group in TREE.species_groups(PLAS.split("+"))
    )

    assert _units(f"{PLAS}>=55T AND {TOXO}=0T") == []
    assert _units(every_species) == []


@pytest.mark.parametrize(
    ("message", "named"),
    [
        (
            (
                "List the ortholog groups that have exactly one protein in every "
                "apicomplexan genome."
            ),
            True,
        ),
        (
            (
                "Which ortholog groups are present in all Plasmodium species but "
                "absent from Toxoplasma gondii?"
            ),
            False,
        ),
        ("Keep the groups found in every sequenced strain.", True),
        ("Groups conserved genome-wide in Plasmodium species.", False),
    ],
)
def test_a_request_names_genomes_by_its_words(message: str, named: bool) -> None:
    assert names_genomes([message]) is named
