"""Which compare reading answers which comparison of two genome sets, and the
bound terms that do not answer the reading a framing pass classed a request by."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from veupathdb.domain.parameters import PhyleticTree
from veupathdb_mcp.catalog import CompareTerm, PhyleticPattern

from pathfinder.domain.count_words import counted
from pathfinder.domain.strategy.pattern_sets import compare_terms, genomes_of

type CompareReading = Literal["per_genome", "totals", "averages"]

READING_RULES: dict[CompareReading, str] = {
    "per_genome": (
        "per_genome answers a question about each genome, every genome of one set "
        "against every genome of the other"
    ),
    "totals": (
        "totals answers a question about the sets pooled, all proteins of one set "
        "against all proteins of the other"
    ),
    "averages": (
        "averages answers a question about proteins per genome, an average or a "
        "ratio, each set's proteins divided by its genome count"
    ),
}


def _shown(term: CompareTerm, tree: PhyleticTree) -> tuple[str, str, bool]:
    left = genomes_of(term.left, tree)
    right = genomes_of(term.right, tree)
    single = len(left) == 1 and len(right) == 1
    return (
        f"{term.left.outline()} ({counted(len(left), 'genome')})",
        f"{term.right.outline()} ({counted(len(right), 'genome')})",
        single,
    )


def _departure(
    criterion_id: str, term: CompareTerm, asked: CompareReading, tree: PhyleticTree
) -> str | None:
    left, right, single = _shown(term, tree)
    if term.reading == asked or single:
        return None
    return (
        f"{criterion_id} compares {left} with {right} by {term.reading}, and the "
        f"request asks for {asked}: {READING_RULES[asked]}. Build the compare again "
        f"with reading {asked} and bind its handle."
    )


def reading_departures(
    asked: CompareReading,
    bound: Sequence[tuple[str, PhyleticPattern]],
    tree: PhyleticTree,
) -> list[str]:
    """Why the bound patterns do not answer a comparison of the asked reading."""
    terms = [(cid, term) for cid, held in bound for term in compare_terms(held)]
    if bound and not terms:
        ids = ", ".join(cid for cid, _ in bound)
        return [
            (
                f"The request compares two sets of genomes, and {ids} binds no "
                "compare term. Build it with build_phyletic_expression as a compare "
                f"with reading {asked} and bind its handle: a count over one genome "
                "does not answer a comparison of two sets."
            )
        ]
    return [
        sentence
        for cid, term in terms
        if (sentence := _departure(cid, term, asked, tree)) is not None
    ]


__all__ = ["READING_RULES", "CompareReading", "reading_departures"]
