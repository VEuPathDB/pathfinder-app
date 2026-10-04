"""Read-only answers from one catalog search run as an anonymous report: how
many genes it returns, and which of a list of gene ids it holds. Neither
creates a step or a strategy."""

from __future__ import annotations

from collections.abc import Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from veupathdb.domain.parameters import wire_map
from veupathdb_mcp.wdk import extract_pk

from pathfinder.domain.comparison_facts import (
    ComparedVariant,
    ComparisonFact,
    SharedGenes,
)
from pathfinder.services.experiment.variant_comparison import (
    VariantSpec,
    run_variant_search,
)

# The label the asked genes carry in a membership check's comparison.
ASKED_GENES = "asked genes"


class SearchCount(CamelModel):
    """The genes one search returns, with the wire value of each parameter it ran."""

    label: str
    search_name: str
    values: dict[str, str] = Field(default_factory=dict)
    gene_count: int

    def fact(self) -> ComparisonFact:
        """The count as a comparison of one variant, which every gene is unique to."""
        counted = ComparedVariant(
            label=self.label, gene_count=self.gene_count, unique_count=self.gene_count
        )
        return ComparisonFact(variants=[counted])


class SearchMembership(CamelModel):
    """Which of the asked gene ids one search holds, in the order they were asked.

    ``unread`` holds the asked ids past the capped read of the search, which
    the search may hold; it is empty when the read holds the whole result.
    """

    label: str
    search_name: str
    values: dict[str, str] = Field(default_factory=dict)
    gene_count: int
    held: list[str] = Field(default_factory=list)
    not_held: list[str] = Field(default_factory=list)
    unread: list[str] = Field(default_factory=list)

    def fact(self) -> ComparisonFact:
        """The asked genes and the search as two gene sets, and the genes both hold."""
        asked = len(self.held) + len(self.not_held) + len(self.unread)
        shared = len(self.held)
        return ComparisonFact(
            variants=[
                ComparedVariant(
                    label=ASKED_GENES, gene_count=asked, unique_count=len(self.not_held)
                ),
                ComparedVariant(
                    label=self.label,
                    gene_count=self.gene_count,
                    unique_count=self.gene_count - shared,
                ),
            ],
            overlaps=[SharedGenes(a=ASKED_GENES, b=self.label, shared=shared)],
        )


def _membership_of(
    spec: VariantSpec, asked: Sequence[str], found: Sequence[str], total: int
) -> SearchMembership:
    """Which asked ids the found ids hold. An id the found ids lack is not held
    only when they are the whole result of ``total`` genes."""
    held = set(found)
    complete = len(held) >= total
    ordered = list(dict.fromkeys(asked))
    return SearchMembership(
        label=spec.label,
        search_name=spec.search_name,
        values=wire_map(spec.parameters),
        gene_count=total,
        held=[gene for gene in ordered if gene in held],
        not_held=[gene for gene in ordered if gene not in held and complete],
        unread=[gene for gene in ordered if gene not in held and not complete],
    )


async def search_count(site_id: str, spec: VariantSpec) -> SearchCount:
    """How many genes the search returns, read from its report's count."""
    answer = await run_variant_search(site_id, spec)
    return SearchCount(
        label=spec.label,
        search_name=spec.search_name,
        values=wire_map(spec.parameters),
        gene_count=answer.meta.records_returned(),
    )


async def search_membership(
    site_id: str, spec: VariantSpec, asked: Sequence[str]
) -> SearchMembership:
    """Which of the asked gene ids the search holds, from its capped id read."""
    answer = await run_variant_search(site_id, spec)
    found = [gene for record in answer.records if (gene := extract_pk(record))]
    return _membership_of(spec, asked, found, answer.meta.records_returned())


__all__ = [
    "ASKED_GENES",
    "SearchCount",
    "SearchMembership",
    "search_count",
    "search_membership",
]
