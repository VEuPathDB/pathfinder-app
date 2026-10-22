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
        and unit.count >= FEW_GENOMES
        and unit.count == len(tree.genomes_under(unit.codes))
        and frozenset(tree.genomes_under(unit.codes)) not in counted
    ]
    return [
        unit
        for unit in found
        if _readings(unit, tree).share_differs or _readings(unit, tree).species_differ
    ]


def names_genomes(messages: Sequence[str]) -> bool:
    return any(_GENOME_WORD.search(message) for message in messages)


__all__ = [
    "FEW_GENOMES",
    "SHARE_PERCENT",
    "PresenceReadings",
    "UnitReadings",
    "every_genome_units",
    "names_genomes",
    "presence_readings",
    "share_of",
]
