"""The length, split and pseudogene-call candidates of a screened genome, from the collected gene reports."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from veupathdb_mcp.audit import (
    SPLIT_MAX_GAP,
    GeneRow,
    call_length,
    classify,
    pseudogene_calls_of,
)

from pathfinder.domain.audit.scope import (
    GenePairTarget,
    GeneTarget,
    ScreenedCheck,
    SingleGeneTarget,
)


class Candidate(CamelModel):
    model_config = ConfigDict(frozen=True)

    genome: str
    target: GeneTarget


def ortholog_groups(rows: Iterable[GeneRow]) -> dict[str, list[GeneRow]]:
    groups: defaultdict[str, list[GeneRow]] = defaultdict(list)
    for row in rows:
        if row.ortholog_group:
            groups[row.ortholog_group].append(row)
    return dict(groups)


def _screened(row: GeneRow) -> bool:
    coding = not row.pseudo and "protein" in row.gene_type
    return bool(row.ortholog_group) and coding and bool(row.protein_length)


def audited_groups(audited: Mapping[str, list[GeneRow]]) -> frozenset[str]:
    return frozenset(
        row.ortholog_group
        for rows in audited.values()
        for row in rows
        if _screened(row)
    )


def _neighbours(first: GeneRow, second: GeneRow) -> bool:
    gap = max(first.start, second.start) - min(first.end, second.end)
    same_place = (first.sequence_id, first.strand) == (
        second.sequence_id,
        second.strand,
    )
    return same_place and gap <= SPLIT_MAX_GAP


def _place(row: GeneRow) -> tuple[str, int, str]:
    return (row.sequence_id, row.start, row.gene)


def _only_pair(members: list[GeneRow]) -> tuple[GeneRow, GeneRow] | None:
    match sorted(members, key=_place):
        case [first, second] if _neighbours(first, second):
            return (first, second)
        case _:
            return None


def split_pairs(rows: Sequence[GeneRow]) -> list[tuple[GeneRow, GeneRow]]:
    members: defaultdict[tuple[str, str], list[GeneRow]] = defaultdict(list)
    for row in rows:
        if _screened(row):
            members[(row.organism, row.ortholog_group)].append(row)
    pairs = [pair for group in members.values() if (pair := _only_pair(group))]
    return sorted(pairs, key=lambda pair: _place(pair[0]))


def _splits(
    rows: Sequence[GeneRow], groups: Mapping[str, list[GeneRow]]
) -> list[GenePairTarget]:
    return [
        GenePairTarget(check="gene_split", genes=(first.gene, second.gene))
        for first, second in split_pairs(rows)
        if call_length([first, second], groups[first.ortholog_group]).length_class
        == "SPLIT"
    ]


def _lengths(
    rows: Sequence[GeneRow], groups: Mapping[str, list[GeneRow]]
) -> list[SingleGeneTarget]:
    return [
        SingleGeneTarget(check="gene_length", genes=(row.gene,))
        for row in rows
        if _screened(row) and classify(row, groups[row.ortholog_group]) == "SHORT"
    ]


def screen_genome(
    genome: str,
    checks: tuple[ScreenedCheck, ...],
    rows: Sequence[GeneRow],
    groups: Mapping[str, list[GeneRow]],
) -> list[Candidate]:
    splits = _splits(rows, groups) if "gene_split" in checks else []
    lengths = _lengths(rows, groups) if "gene_length" in checks else []
    return [Candidate(genome=genome, target=target) for target in (*splits, *lengths)]


def screen_genomes(
    checks: tuple[ScreenedCheck, ...],
    audited: Mapping[str, list[GeneRow]],
    comparison: Sequence[GeneRow],
) -> list[Candidate]:
    groups = ortholog_groups(
        [*(row for rows in audited.values() for row in rows), *comparison]
    )
    return [
        candidate
        for genome, rows in audited.items()
        for candidate in screen_genome(genome, checks, rows, groups)
    ]


def pseudogene_candidates(
    reference_organism: str,
    reference: list[GeneRow],
    genomes: Mapping[str, list[GeneRow]],
) -> list[Candidate]:
    return [
        Candidate(
            genome=genome,
            target=GenePairTarget(
                check="pseudogene_call", genes=(call.pseudogene, call.reference_gene)
            ),
        )
        for genome, rows in genomes.items()
        if genome != reference_organism
        for call in pseudogene_calls_of(
            genome, reference_organism, rows, reference
        ).calls
    ]
