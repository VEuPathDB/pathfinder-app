from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from itertools import pairwise

from assistant_core.graph.tool_summary import count_noun
from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import (
    PhyleticExpression,
    PhyleticTree,
    TaxaCount,
    species_of,
)

_NOUNS = {True: "genome", False: "protein"}
_TWO = 2

type _Side = tuple[tuple[str, ...], bool]
type _Limits = tuple[int, int | None]
type _Kind = tuple[str, int, bool]


class _Whole(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    genomes: frozenset[str]
    species: int


class _Span(BaseModel):
    model_config = ConfigDict(frozen=True)

    size: int
    text: str


class _Band(BaseModel):
    model_config = ConfigDict(frozen=True)

    low: int
    high: int
    floor: int


class _Comparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    bounded: _Side
    floored: _Side
    bands: tuple[_Band, ...]


def _up_to(top: int) -> tuple[str, int]:
    if top < 1:
        return f"at most {top}", top
    if top == 1:
        return "exactly 1", top
    return f"1 to {top}", top


def _bound(unit: TaxaCount) -> tuple[str, int]:
    match unit.op:
        case ">=":
            return f"at least {unit.count}", unit.count
        case ">":
            return f"more than {unit.count}", unit.count
        case "=":
            return f"exactly {unit.count}", unit.count
        case "<=":
            return _up_to(unit.count)
        case "<":
            return _up_to(unit.count - 1)


def _noun(top: int, *, taxa: bool) -> str:
    return _NOUNS[taxa] if top == 1 else f"{_NOUNS[taxa]}s"


def _absent(unit: TaxaCount) -> bool:
    return unit.op == "=" and unit.count == 0


def _condition(unit: TaxaCount) -> str:
    if _absent(unit):
        return f"no {_NOUNS[unit.taxa]}"
    words, top = _bound(unit)
    return f"{words} {_noun(top, taxa=unit.taxa)}"


def _limits(unit: TaxaCount) -> _Limits:
    match unit.op:
        case "=":
            return unit.count, unit.count
        case ">=":
            return unit.count, None
        case ">":
            return unit.count + 1, None
        case "<=":
            return 1, unit.count
        case "<":
            return 1, unit.count - 1


def _merged(limits: Sequence[_Limits]) -> _Limits:
    highs = [high for _, high in limits if high is not None]
    return max(low for low, _ in limits), min(highs) if highs else None


def _sides(units: Iterable[TaxaCount]) -> dict[_Side, _Limits]:
    held: defaultdict[_Side, list[_Limits]] = defaultdict(list)
    for unit in units:
        held[tuple(sorted(unit.codes)), unit.taxa].append(_limits(unit))
    return {side: _merged(limits) for side, limits in held.items()}


def _band(bounded: _Limits, floored: _Limits) -> _Band | None:
    low, high = bounded
    floor, ceiling = floored
    if high is None or ceiling is not None:
        return None
    return _Band(low=low, high=high, floor=floor)


def _comparison(terms: Sequence[Sequence[TaxaCount]]) -> _Comparison | None:
    read = [_sides(units) for units in terms]
    keys = list(read[0])
    if len(terms) < _TWO or len(keys) != _TWO or any(set(r) != set(keys) for r in read):
        return None
    for bounded, floored in (keys, keys[::-1]):
        found = [_band(r[bounded], r[floored]) for r in read]
        bands = sorted(
            (band for band in found if band is not None), key=lambda b: b.low
        )
        if len(bands) == len(read) and all(
            one.high < next_one.low and one.floor < next_one.floor
            for one, next_one in pairwise(bands)
        ):
            return _Comparison(bounded=bounded, floored=floored, bands=tuple(bands))
    return None


def _offset(comparison: _Comparison) -> int | None:
    bands = comparison.bands
    offsets = {band.floor - band.low for band in bands}
    exact = all(band.low == band.high for band in bands)
    consecutive = bands[-1].low - bands[0].low == len(bands) - 1
    same_unit = comparison.bounded[1] == comparison.floored[1]
    if len(offsets) != 1 or not (exact and consecutive and same_unit):
        return None
    offset = offsets.pop()
    return offset if offset >= 1 else None


class _Taxa:
    def __init__(self, tree: PhyleticTree) -> None:
        self.tree = tree
        self.labels = {node.code: node.label for node in tree.nodes()}
        genomes = [node for node in tree.nodes() if not node.clade]
        self.species_named = {node.code: species_of(node.label) for node in genomes}
        groups = tree.species_groups([node.code for node in genomes])
        self.species = {one.species: frozenset(one.genomes) for one in groups}
        self.wholes = sorted(self._named(), key=lambda whole: -len(whole.genomes))

    def _whole(self, name: str, genomes: frozenset[str]) -> _Whole:
        species = len({self.species_named[genome] for genome in genomes})
        return _Whole(name=name, genomes=genomes, species=species)

    def _named(self) -> Iterator[_Whole]:
        genera: defaultdict[str, set[str]] = defaultdict(set)
        for species, genomes in self.species.items():
            genera[species.split()[0]].update(genomes)
            if len(genomes) > 1:
                yield self._whole(species, genomes)
        for genus, held in genera.items():
            whole = self._whole(genus, frozenset(held))
            if whole.species > 1:
                yield whole
        for node in self.tree.nodes():
            below = frozenset(self.tree.genomes_under([node.code]))
            if node.clade and len(below) > 1:
                yield self._whole(node.label, below)

    @staticmethod
    def _cover(
        genomes: Iterable[str], wholes: Iterable[_Whole]
    ) -> tuple[list[_Whole], set[str]]:
        left = set(genomes)
        taken = []
        for whole in wholes:
            if whole.genomes <= left:
                taken.append(whole)
                left -= whole.genomes
        return taken, left

    def _partial(self, genomes: set[str]) -> list[str]:
        pieces = []
        for group in self.tree.species_groups(sorted(genomes)):
            labels = [self.labels[code] for code in group.genomes]
            if len(labels) == 1:
                pieces.extend(labels)
                continue
            kept = ", ".join(
                label.removeprefix(f"{group.species} ") for label in labels
            )
            pieces.append(
                f"{len(labels)} of the {len(self.species[group.species])} genomes of "
                f"{group.species}: {kept}"
            )
        return pieces

    def span(self, codes: Sequence[str]) -> _Span:
        genomes = self.tree.genomes_under(codes)
        unplaced = [
            self.labels.get(code, code)
            for code in sorted(codes)
            if not self.tree.genomes_under([code])
        ]
        wholes, left = self._cover(genomes, self.wholes)
        rest = [*self._partial(left), *unplaced]
        size = len(genomes) + len(unplaced)
        if size == 1:
            return _Span(size=size, text=rest[0])
        if not rest:
            names = ", ".join(whole.name for whole in wholes)
            return _Span(size=size, text=f"the {size} genomes of {names}")
        whole_sizes = [f"{w.name} (all {len(w.genomes)})" for w in wholes]
        listed = ", ".join([*whole_sizes, *rest])
        return _Span(size=size, text=f"these {size} ({listed})")

    def clause(self, unit: TaxaCount) -> str:
        span = self.span(unit.codes)
        if _absent(unit):
            if unit.taxa and span.size > 1:
                return f"none of {span.text}"
            return f"no protein in {span.text}"
        words, top = _bound(unit)
        if not unit.taxa:
            return f"{words} {_noun(top, taxa=False)} in {span.text}"
        if span.size == 1:
            return f"{words} {_noun(top, taxa=True)} of {span.text}"
        if unit.op in {"=", ">="} and unit.count == span.size:
            return f"all of {span.text}"
        return f"{words} of {span.text}"

    def _one_species(self, unit: TaxaCount) -> bool:
        genomes = self.tree.genomes_under(unit.codes)
        names = {self.species_named[genome] for genome in genomes}
        return len(names) == 1 and genomes == self.species[names.pop()]

    def _in_each(self, members: Sequence[TaxaCount]) -> str:
        genomes = self.tree.genomes_under([c for u in members for c in u.codes])
        names = sorted({self.species_named[genome] for genome in genomes})
        higher = [whole for whole in self.wholes if whole.species > 1]
        groups, _ = self._cover(genomes, higher)
        covered = {self.species_named[g] for whole in groups for g in whole.genomes}
        others = [name for name in names if name not in covered]
        pieces = [f"the {w.species} species of {w.name}" for w in groups]
        pieces.extend(others)
        total = f"{len(genomes)} genomes"
        where = (
            f"{pieces[0]} ({total})"
            if len(groups) == 1 and not others
            else f"{len(names)} species ({total}: {', '.join(pieces)})"
        )
        link = "any" if _absent(members[0]) else "each"
        return f"{_condition(members[0])} in {link} of {where}"

    def term(self, units: Sequence[TaxaCount]) -> str:
        by_kind: defaultdict[_Kind, list[TaxaCount]] = defaultdict(list)
        for unit in units:
            if self._one_species(unit):
                by_kind[unit.op, unit.count, unit.taxa].append(unit)
        parts = []
        said: set[_Kind] = set()
        for unit in units:
            kind = unit.op, unit.count, unit.taxa
            members = by_kind[kind]
            if len(members) < _TWO or unit not in members:
                parts.append(self.clause(unit))
            elif kind not in said:
                said.add(kind)
                parts.append(self._in_each(members))
        return " and ".join(parts)

    def compared(self, comparison: _Comparison) -> str:
        bands = comparison.bands
        (bounded, bounded_taxa), (floored, floored_taxa) = (
            comparison.bounded,
            comparison.floored,
        )
        low_side = self.span(bounded).text
        high_side = self.span(floored).text
        unit = _NOUNS[bounded_taxa]
        offset = _offset(comparison)
        if offset is not None:
            return (
                f"at least {offset} more {_noun(offset, taxa=bounded_taxa)} in {high_side} "
                f"than in {low_side}, while {low_side} holds {bands[0].low} to "
                f"{bands[-1].low} {unit}s ({len(bands)} OR terms)"
            )
        steps = "; ".join(
            f"{_range(band)} with at least {band.floor}" for band in bands
        )
        return (
            f"{len(bands)} bands of the {unit}s in {low_side}, each with a floor on "
            f"the {_NOUNS[floored_taxa]}s in {high_side}: {steps}"
        )


def _range(band: _Band) -> str:
    if band.low == band.high:
        return f"exactly {band.low}"
    return f"{band.low} to {band.high}"


def _terms(expression: PhyleticExpression) -> list[list[TaxaCount]]:
    terms = expression.site_reading().root.operands("OR")
    return [PhyleticExpression(root=term).units() for term in terms]


def _clause_sizes(terms: Sequence[Sequence[TaxaCount]]) -> str:
    sizes = sorted({len(units) for units in terms})
    if len(sizes) == 1:
        return count_noun(sizes[0], "AND clause")
    return f"{sizes[0]} to {sizes[-1]} AND clauses"


def _tally(units: Iterable[TaxaCount]) -> str:
    counted = Counter(_condition(unit) for unit in units)
    return ", ".join(f"{count} of {condition}" for condition, count in counted.items())


def _fold(taxa: _Taxa, terms: Sequence[Sequence[TaxaCount]]) -> str:
    if len(terms) == 1:
        return taxa.term(terms[0])
    return " or ".join(f"({taxa.term(units)})" for units in terms)


def condensed_reading(
    expression: PhyleticExpression, length: int, tree: PhyleticTree, limit: int
) -> str:
    taxa = _Taxa(tree)
    terms = _terms(expression)
    codes = len(expression.codes())
    comparison = _comparison(terms)
    if len(terms) > 1:
        shape = (
            f"names {codes} codes in {len(terms)} OR terms of {_clause_sizes(terms)}, "
            f"{length:,} characters"
        )
        detail = (
            f"{shape}; first term: {taxa.term(terms[0])}; "
            f"last term: {taxa.term(terms[-1])}"
        )
    else:
        shape = (
            f"names {codes} codes in {count_noun(len(terms[0]), 'AND clause')}, "
            f"{length:,} characters"
        )
        detail = f"{shape}: {_tally(terms[0])}"
    candidates = [
        *([] if comparison is None else [taxa.compared(comparison)]),
        _fold(taxa, terms),
        detail,
    ]
    return next((one for one in candidates if len(one) <= limit), shape)


__all__ = ["condensed_reading"]
