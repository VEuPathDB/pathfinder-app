from __future__ import annotations

from collections.abc import Iterator
from fractions import Fraction
from math import ceil, floor

from pydantic import TypeAdapter, ValidationError
from veupathdb.domain.parameters import PhyleticTree
from veupathdb_mcp.catalog import (
    AllExcept,
    AllOf,
    AnyOf,
    CodeSet,
    CompareTerm,
    CountTerm,
    EachGenomeOf,
    EachSpeciesOf,
    NoneOf,
    PhyleticPattern,
)

from pathfinder.domain.strategy.constraints import GenomeShape
from pathfinder.domain.strategy.pattern_sets import NamedSet, genomes_of

type Span = tuple[int, int | None]
type PartKey = tuple[frozenset[str], bool | None, Span | None]
type TermKey = tuple[object, ...]

_WHOLE = 100
_COUNT: TypeAdapter[CountTerm] = TypeAdapter(CountTerm)
_NONE: Span = (0, 0)
_SOME: Span = (1, None)


def _span(condition: str, x: Fraction) -> Span | None:
    match condition:
        case "absent":
            return _NONE
        case "at_least":
            return ceil(x), None
        case "more_than":
            return floor(x) + 1, None
        case "at_most":
            return 0, floor(x)
        case "fewer_than":
            return None if ceil(x) < 1 else (0, ceil(x) - 1)
        case _:
            return (int(x), int(x)) if x.denominator == 1 else None


def _parts(named: NamedSet, tree: PhyleticTree) -> list[frozenset[str]]:
    match named:
        case EachGenomeOf():
            return [frozenset({genome}) for genome in genomes_of(named, tree)]
        case EachSpeciesOf():
            return [frozenset(g.genomes) for g in tree.species_groups(named.codes)]
        case CodeSet() | AllExcept():
            return [genomes_of(named, tree)]


def _part_key(term: CountTerm, part: frozenset[str]) -> PartKey:
    taxa = term.measure != "proteins"
    if term.value is None:
        return part, None, _NONE
    value = Fraction(str(term.value))
    if term.measure == "share":
        value = value * len(part) / _WHOLE
    span = _span(term.condition, value)
    if span is not None and taxa:
        lo, hi = span
        top = len(part) if hi is None else min(hi, len(part))
        span = None if top < lo else (lo, None if top == len(part) else top)
    if span in (_NONE, _SOME):
        return part, None, span
    return part, taxa, span


def _count_key(term: CountTerm, tree: PhyleticTree) -> TermKey | None:
    parts = _parts(term.of, tree)
    if not parts or not all(parts):
        return None
    return ("count", frozenset(_part_key(term, part) for part in parts))


def _compare_key(term: CompareTerm, tree: PhyleticTree) -> TermKey | None:
    left = genomes_of(term.left, tree)
    right = genomes_of(term.right, tree)
    if not left or not right:
        return None
    factor = Fraction(str(term.factor))
    return ("compare", term.reading, term.condition, factor, left, right)


def _absent(key: TermKey) -> TermKey | None:
    match key:
        case ("count", frozenset() as parts):
            if all(span == _SOME for _, _, span in parts):
                return ("count", frozenset((p, None, _NONE) for p, _, _ in parts))
            return None
        case _:
            return None


def _key(term: PhyleticPattern, tree: PhyleticTree) -> TermKey | None:
    match term:
        case CountTerm():
            return _count_key(term, tree)
        case CompareTerm():
            return _compare_key(term, tree)
        case NoneOf(terms=[only]):
            held = _key(only, tree)
            return None if held is None else _absent(held)
        case AllOf() | AnyOf() | NoneOf():
            return None


def _conjuncts(pattern: PhyleticPattern) -> Iterator[PhyleticPattern]:
    match pattern:
        case AllOf():
            for term in pattern.terms:
                yield from _conjuncts(term)
        case _:
            yield pattern


def states_clause(
    pattern: PhyleticPattern, clause: PhyleticPattern, tree: PhyleticTree
) -> bool:
    held = {_key(term, tree) for term in _conjuncts(pattern)} - {None}
    wanted = [_key(term, tree) for term in _conjuncts(clause)]
    return all(key is not None and key in held for key in wanted)


def _shaped_count(clause: CountTerm, shape: GenomeShape) -> CountTerm | None:
    raw = {
        "kind": "count",
        "of": {"kind": shape.scope, "codes": clause.of.codes},
        "measure": shape.measure,
        "condition": shape.condition,
        "value": shape.value,
    }
    try:
        return _COUNT.validate_python(raw)
    except ValidationError:
        return None


def matches_shape(
    clause: PhyleticPattern, shape: GenomeShape, tree: PhyleticTree
) -> bool:
    match clause:
        case CountTerm() if shape.kind == "count":
            shaped = _shaped_count(clause, shape)
            key = None if shaped is None else _count_key(shaped, tree)
            return key is not None and key == _count_key(clause, tree)
        case CompareTerm() if shape.kind == "compare":
            return (shape.reading, shape.condition, Fraction(str(shape.factor))) == (
                clause.reading,
                clause.condition,
                Fraction(str(clause.factor)),
            )
        case _:
            return False


__all__ = ["matches_shape", "states_clause"]
