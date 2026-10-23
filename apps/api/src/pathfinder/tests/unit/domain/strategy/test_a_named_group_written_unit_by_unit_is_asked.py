from __future__ import annotations

import math

from veupathdb.domain.parameters import PhyleticExpression

from pathfinder.domain.strategy.every_genome import asked_units
from pathfinder.domain.strategy.named_groups import (
    GroupScope,
    scoped_taxa,
    whole_taxa,
)
from pathfinder.tests._support.ortho_taxonomy import (
    labelled_genomes,
    recorded_ortho_taxonomy,
)

TREE = recorded_ortho_taxonomy()
PLAS = labelled_genomes(TREE, "Plasmodium ")
TOXO = "+".join(labelled_genomes(TREE, "Toxoplasma "))
GROUPS = [
    taxon.required
    for taxon in whole_taxa(
        scoped_taxa({}, [GroupScope(taxon="Plasmodium", scope="whole")], [], TREE)
    )
]
SPECIES = TREE.species_groups(PLAS)


def _per_species(genomes: list[str]) -> str:
    return " AND ".join(
        f"{'+'.join(g for g in group.genomes if g in genomes)}"
        f">={math.ceil(len(group.genomes) / 2)}T"
        for group in TREE.species_groups(genomes)
    )


def _asked(text: str) -> list[tuple[str, int]]:
    return [
        (unit.op, unit.count)
        for unit in asked_units(PhyleticExpression.parse(text), TREE, GROUPS)
    ]


def test_every_species_of_a_named_group_is_asked_as_the_group() -> None:
    (unit,) = asked_units(
        PhyleticExpression.parse(f"{_per_species(PLAS)} AND {TOXO}=0T"), TREE, GROUPS
    )

    assert set(TREE.genomes_under(unit.codes)) == set(PLAS)
    assert (unit.op, unit.count, unit.taxa) == ("=", len(PLAS), True)


def test_every_genome_one_unit_at_a_time_is_asked_as_the_group() -> None:
    assert _asked(" AND ".join(f"{code}>=1T" for code in PLAS)) == [("=", len(PLAS))]


def test_a_species_reading_with_no_whole_group_is_not_asked() -> None:
    text = _per_species(PLAS)

    assert asked_units(PhyleticExpression.parse(text), TREE, []) == []


def test_units_that_leave_genomes_of_the_group_out_are_not_asked() -> None:
    kept = [code for code in PLAS if code not in {"pccb", "pcym"}]

    assert _asked(" AND ".join(f"{code}>=1T" for code in kept)) == []


def test_units_joined_by_or_are_not_asked() -> None:
    assert _asked(" OR ".join(f"{code}>=1T" for code in PLAS)) == []


def test_units_that_count_the_groups_proteins_are_not_asked() -> None:
    every = " AND ".join(f"{code}=1T" for code in PLAS)

    assert _asked(f"{every} AND {'+'.join(PLAS)}={len(PLAS)}") == []


def test_one_list_at_its_length_is_asked_once() -> None:
    assert _asked(f"{'+'.join(PLAS)}={len(PLAS)}T AND {TOXO}=0T") == [("=", len(PLAS))]


def test_absence_from_the_group_is_not_asked() -> None:
    assert _asked(" AND ".join(f"{code}=0T" for code in PLAS)) == []


def test_a_share_of_the_group_in_one_unit_is_not_asked() -> None:
    assert _asked(f"{'+'.join(PLAS)}>={len(PLAS) - 6}T AND {TOXO}=0T") == []


def test_a_group_its_list_already_asks_about_is_asked_once() -> None:
    every = f"{'+'.join(PLAS)}={len(PLAS)}T"

    assert _asked(f"{every} AND {_per_species(PLAS)}") == [("=", len(PLAS))]
