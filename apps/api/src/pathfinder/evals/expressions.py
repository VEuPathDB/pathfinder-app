"""A phyletic expression as the site reads it, reduced to a normal form, so two
writings of one meaning grade equal."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    Combination,
    PhyleticExpression,
    PhyleticTree,
    TaxaCount,
)
from veupathdb.errors import ValidationError

from pathfinder.evals.difference import CaseDifference
from pathfinder.evals.distance import ComparisonNode


class Unit(BaseModel):
    model_config = ConfigDict(frozen=True)

    genomes: frozenset[str]
    taxa: bool
    low: int
    high: int | None


class Meaning(BaseModel):
    model_config = ConfigDict(frozen=True)

    join: Literal["AND", "OR"]
    units: frozenset[Unit]
    terms: frozenset[Meaning]


def _bounds(unit: TaxaCount) -> tuple[int, int | None]:
    match unit.op:
        case "=":
            return unit.count, unit.count
        case ">=":
            return unit.count, None
        case ">":
            return unit.count + 1, None
        case "<=":
            return 0, unit.count
        case "<":
            return 0, unit.count - 1


def _unit(unit: TaxaCount, tree: PhyleticTree) -> Unit:
    genomes = frozenset(tree.genomes_under(unit.codes))
    low, high = _bounds(unit)
    if unit.op == "=" and unit.count == 0:
        return Unit(genomes=genomes, taxa=False, low=0, high=0)
    low = max(low, 1)
    if not unit.taxa:
        return Unit(genomes=genomes, taxa=False, low=low, high=high)
    high = len(genomes) if high is None else min(high, len(genomes))
    if low == 1 and high == len(genomes):
        return Unit(genomes=genomes, taxa=False, low=1, high=None)
    return Unit(genomes=genomes, taxa=True, low=low, high=high)


def _lower(a: int | None, b: int | None) -> int | None:
    return b if a is None else a if b is None else min(a, b)


def _intersected(units: Iterable[Unit]) -> list[Unit]:
    merged: dict[tuple[frozenset[str], bool], Unit] = {}
    for unit in units:
        key = (unit.genomes, unit.taxa)
        held = merged.get(key, unit)
        merged[key] = unit.model_copy(
            update={
                "low": max(held.low, unit.low),
                "high": _lower(held.high, unit.high),
            }
        )
    return list(merged.values())


def _each(genomes: frozenset[str], low: int, high: int | None) -> list[Unit]:
    return [
        Unit(genomes=frozenset({genome}), taxa=False, low=low, high=high)
        for genome in sorted(genomes)
    ]


def _expanded(unit: Unit) -> list[Unit]:
    size = len(unit.genomes)
    if size <= 1:
        return [unit]
    if not unit.taxa and unit.low == unit.high == 0:
        return _each(unit.genomes, 0, 0)
    if unit.taxa and unit.low == unit.high == size:
        return _each(unit.genomes, 1, None)
    return [unit]


def _single_copy(units: list[Unit]) -> list[Unit]:
    present = {
        genome
        for unit in units
        if len(unit.genomes) == 1 and not unit.taxa and unit.low >= 1
        for genome in unit.genomes
    }
    single = [
        unit
        for unit in units
        if not unit.taxa
        and len(unit.genomes) > 1
        and unit.genomes <= present
        and unit.low <= len(unit.genomes) == unit.high
    ]
    kept = [unit for unit in units if unit not in single]
    copies = [copy for unit in single for copy in _each(unit.genomes, 1, 1)]
    return _intersected([*kept, *copies])


def _implied(unit: Unit, units: list[Unit]) -> bool:
    if unit.taxa or unit.low != 1 or unit.high is not None:
        return False
    return any(
        other != unit
        and other.low >= 1
        and other.genomes
        and other.genomes <= unit.genomes
        for other in units
    )


def _conjunction(units: list[Unit]) -> list[Unit]:
    spread = [part for unit in _intersected(units) for part in _expanded(unit)]
    whole = _single_copy(_intersected(spread))
    return [unit for unit in whole if not _implied(unit, whole)]


def _joined(
    join: Literal["AND", "OR"], units: list[Unit], terms: list[Meaning]
) -> Meaning:
    if join == "AND":
        units = _conjunction(units)
    held, nested = frozenset(units), frozenset(terms)
    if not held and len(nested) == 1:
        return next(iter(nested))
    if len(held) == 1 and not nested:
        return Meaning(join="AND", units=held, terms=frozenset())
    return Meaning(join=join, units=held, terms=nested)


def _meaning(term: TaxaCount | Combination, tree: PhyleticTree) -> Meaning:
    match term:
        case TaxaCount():
            return _joined("AND", [_unit(term, tree)], [])
        case Combination(join=join, terms=parts):
            units: list[Unit] = []
            nested: list[Meaning] = []
            for child in (_meaning(part, tree) for part in parts):
                if child.join == join or (len(child.units) == 1 and not child.terms):
                    units.extend(child.units)
                    nested.extend(child.terms)
                else:
                    nested.append(child)
            return _joined(join, units, nested)


def meaning(expression: PhyleticExpression, tree: PhyleticTree) -> Meaning:
    return _meaning(expression.root, tree)


def _meaning_of(text: str, tree: PhyleticTree) -> Meaning | None:
    try:
        return meaning(PhyleticExpression.parse(text).site_reading(), tree)
    except ValidationError:
        return None


def _written(node: ComparisonNode, search: str) -> list[str | None]:
    own = (
        [node.parameters.get(PHYLETIC_EXPRESSION_PARAM)]
        if node.search_name == search
        else []
    )
    return [
        *own,
        *(text for child in node.children for text in _written(child, search)),
    ]


def expression_differences(
    accepted: dict[str, list[str]],
    tree: ComparisonNode | None,
    taxonomy: PhyleticTree | None,
) -> list[CaseDifference]:
    if not accepted:
        return []
    if taxonomy is None:
        return [
            CaseDifference(
                field="expressions", expected="the site's taxonomy", actual="(none)"
            )
        ]
    if tree is None:
        return []
    differences: list[CaseDifference] = []
    for search, writings in sorted(accepted.items()):
        wanted = [
            read
            for text in writings
            if (read := _meaning_of(text, taxonomy)) is not None
        ]
        produced = _written(tree, search)
        actual = (
            ["(no such search)"]
            if not produced
            else [
                text or "(unset)"
                for text in produced
                if text is None or _meaning_of(text, taxonomy) not in wanted
            ]
        )
        differences.extend(
            CaseDifference(
                field=f"expressions.{search}",
                expected=" | ".join(writings),
                actual=value,
            )
            for value in dict.fromkeys(actual)
        )
    return differences


__all__ = [
    "Meaning",
    "Unit",
    "expression_differences",
    "meaning",
]
