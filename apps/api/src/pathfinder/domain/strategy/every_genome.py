"""The units of a phyletic expression that ask for presence in every one of many
genomes where another reading differs, and whether a request names genomes."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import (
    PhyleticExpression,
    PhyleticTree,
    SpeciesGroup,
    TaxaCount,
)

from pathfinder.domain.strategy.named_groups import NamedGroup

FEW_GENOMES = 3
SHARE_PERCENT = 90
_GENOME_WORD = re.compile(
    r"(?<![\w-])(?:genome|strain|isolate|proteome)s?(?![\w-])", re.IGNORECASE
)


def share_of(genomes: int) -> int:
    return math.ceil(genomes * SHARE_PERCENT / 100)


class UnitReadings(BaseModel):
    model_config = ConfigDict(frozen=True)

    genomes: int
    species: tuple[SpeciesGroup, ...]

    @property
    def share(self) -> int:
        return share_of(self.genomes)

    @property
    def share_differs(self) -> bool:
        return self.share < self.genomes

    @property
    def species_differ(self) -> bool:
        return any(len(group.genomes) > 1 for group in self.species)


class PresenceReadings(BaseModel):
    model_config = ConfigDict(frozen=True)

    units: tuple[UnitReadings, ...]

    @property
    def share_differs(self) -> bool:
        return any(unit.share_differs for unit in self.units)

    @property
    def species_differ(self) -> bool:
        return any(unit.species_differ for unit in self.units)


def _readings(unit: TaxaCount, tree: PhyleticTree) -> UnitReadings:
    return UnitReadings(
        genomes=len(tree.genomes_under(unit.codes)),
        species=tuple(tree.species_groups(unit.codes)),
    )


def presence_readings(
    units: Sequence[TaxaCount], tree: PhyleticTree
) -> PresenceReadings:
    return PresenceReadings(units=tuple(_readings(unit, tree) for unit in units))


def _wanted(unit: TaxaCount, tree: PhyleticTree) -> bool:
    readings = _readings(unit, tree)
    return unit.count >= FEW_GENOMES and (
        readings.share_differs or readings.species_differ
    )


def every_genome_units(
    expression: PhyleticExpression, tree: PhyleticTree
) -> list[TaxaCount]:
    counted = {
        frozenset(tree.genomes_under(unit.codes))
        for unit in expression.units()
        if not unit.taxa
    }
    found = [
        unit
        for unit in expression.units()
        if unit.op in {"=", ">="}
        and unit.count == len(tree.genomes_under(unit.codes))
        and frozenset(tree.genomes_under(unit.codes)) not in counted
    ]
    return [unit for unit in found if _wanted(unit, tree)]


def _present(unit: TaxaCount) -> bool:
    return unit.taxa and (unit.op == ">" or (unit.op in {"=", ">="} and unit.count > 0))


def _group_unit(
    units: list[TaxaCount], group: NamedGroup, tree: PhyleticTree
) -> TaxaCount | None:
    inside = [
        unit
        for unit in units
        if _present(unit) and tree.genomes_under(unit.codes) <= group.genomes
    ]
    held = {genome for unit in inside for genome in tree.genomes_under(unit.codes)}
    counted = any(
        not unit.taxa and tree.genomes_under(unit.codes) & group.genomes
        for unit in units
    )
    if len(inside) <= 1 or held != group.genomes or counted:
        return None
    return TaxaCount(
        codes=tuple(sorted(group.genomes)),
        op="=",
        count=len(group.genomes),
        taxa=True,
    )


def asked_units(
    expression: PhyleticExpression,
    tree: PhyleticTree,
    groups: Sequence[NamedGroup],
) -> list[TaxaCount]:
    every = every_genome_units(expression, tree)
    held = {genome for unit in every for genome in tree.genomes_under(unit.codes)}
    read = expression.site_reading()
    units = read.units()
    if len(read.root.operands("AND")) != len(units):
        return every
    found = [
        unit
        for group in groups
        if not group.genomes & held
        and (unit := _group_unit(units, group, tree)) is not None
        and _wanted(unit, tree)
    ]
    return [*every, *found]


def names_genomes(messages: Sequence[str]) -> bool:
    return any(_GENOME_WORD.search(message) for message in messages)


__all__ = [
    "FEW_GENOMES",
    "SHARE_PERCENT",
    "PresenceReadings",
    "UnitReadings",
    "asked_units",
    "every_genome_units",
    "names_genomes",
    "presence_readings",
    "share_of",
]
