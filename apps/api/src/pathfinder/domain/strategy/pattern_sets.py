"""The genome sets a phyletic pattern names, as the site's taxonomy counts them."""

from __future__ import annotations

from collections.abc import Iterator

from pydantic import ConfigDict
from veupathdb.domain.parameters import PHYLETIC_ROOT_CODE, PhyleticTree
from veupathdb.model import CamelModel
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

type NamedSet = CodeSet | AllExcept | EachSpeciesOf | EachGenomeOf

_WORDS = {
    "at_least": "at least",
    "more_than": "more than",
    "exactly": "exactly",
}


class SetSize(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: str
    codes: tuple[str, ...]
    genomes: int


class CountBeyondSet(CamelModel):
    model_config = ConfigDict(frozen=True)

    condition: str
    value: int
    named: str
    genomes: int

    @property
    def sentence(self) -> str:
        return (
            f"{_WORDS[self.condition]} {self.value} genomes of {self.named} asks for "
            f"more genomes than it holds: its codes cover {self.genomes} genomes on "
            "the site's taxonomy. Read each set's genome count from `sets`, or state "
            "the bound as a share."
        )


def genomes_of(named: NamedSet, tree: PhyleticTree) -> frozenset[str]:
    held = frozenset(tree.genomes_under(named.codes))
    match named:
        case AllExcept():
            return frozenset(tree.genomes_under([PHYLETIC_ROOT_CODE])) - held
        case _:
            return held


def _largest_part(named: NamedSet, tree: PhyleticTree) -> int:
    match named:
        case EachGenomeOf():
            return 1 if genomes_of(named, tree) else 0
        case EachSpeciesOf():
            groups = tree.species_groups(named.codes)
            return max((len(group.genomes) for group in groups), default=0)
        case CodeSet() | AllExcept():
            return len(genomes_of(named, tree))


def terms_of(pattern: PhyleticPattern) -> Iterator[CountTerm | CompareTerm]:
    match pattern:
        case AllOf() | AnyOf() | NoneOf():
            for term in pattern.terms:
                yield from terms_of(term)
        case CountTerm() | CompareTerm():
            yield pattern


def _sets_of(term: CountTerm | CompareTerm) -> list[NamedSet]:
    match term:
        case CountTerm():
            return [term.of]
        case CompareTerm():
            return [term.left, term.right]


def set_sizes(pattern: PhyleticPattern, tree: PhyleticTree) -> tuple[SetSize, ...]:
    """Each set the pattern names, once, with the genomes its codes cover."""
    named = [named for term in terms_of(pattern) for named in _sets_of(term)]
    sizes = (
        SetSize(
            kind=one.kind,
            codes=tuple(one.codes),
            genomes=len(genomes_of(one, tree)),
        )
        for one in named
    )
    return tuple(dict.fromkeys(sizes))


def count_terms(pattern: PhyleticPattern) -> Iterator[CountTerm]:
    for term in terms_of(pattern):
        match term:
            case CountTerm():
                yield term
            case CompareTerm():
                continue


def compare_terms(pattern: PhyleticPattern) -> Iterator[CompareTerm]:
    for term in terms_of(pattern):
        match term:
            case CompareTerm():
                yield term
            case CountTerm():
                continue


def _beyond(term: CountTerm, tree: PhyleticTree) -> CountBeyondSet | None:
    if term.measure != "genomes" or term.value is None:
        return None
    if term.condition not in _WORDS:
        return None
    largest = _largest_part(term.of, tree)
    value = int(term.value)
    held = value >= largest if term.condition == "more_than" else value > largest
    if not held:
        return None
    return CountBeyondSet(
        condition=term.condition,
        value=value,
        named=term.of.outline(),
        genomes=largest,
    )


def counts_beyond_their_sets(
    pattern: PhyleticPattern, tree: PhyleticTree
) -> list[CountBeyondSet]:
    """Each genome count no group can reach, because the set holds fewer genomes."""
    return [
        beyond
        for term in count_terms(pattern)
        if (beyond := _beyond(term, tree)) is not None
    ]


__all__ = [
    "CountBeyondSet",
    "SetSize",
    "compare_terms",
    "count_terms",
    "counts_beyond_their_sets",
    "genomes_of",
    "set_sizes",
    "terms_of",
]
