"""Which genes of a screened genome are length or split candidates."""

from __future__ import annotations

import pytest
from veupathdb_mcp.audit import GeneRow, GroupMember, call_length

from pathfinder.domain.audit.scope import GenePairTarget, SingleGeneTarget
from pathfinder.domain.audit.screen import (
    Candidate,
    audited_groups,
    ortholog_groups,
    pseudogene_candidates,
    screen_genome,
    screen_genomes,
    split_pairs,
)
from pathfinder.tests._support.audit import NF54, P3D7, gene_row, relatives
from pathfinder.tests._support.audit_genome_screens import (
    NF54_PIGA_PSEUDOGENE,
    NF54_PIGA_ROW,
    P3D7_PIGA_ROW,
)

SHORT_GROUP = "OG7_0000002"
SHORT = gene_row("NF54_SHORT", NF54, 200, group=SHORT_GROUP, sequence="chr2")
PART_A = gene_row("NF54_A", NF54, 200, start=10000)
PART_B = gene_row("NF54_B", NF54, 210, start=11000)
GROUPS = ortholog_groups(
    [
        SHORT,
        PART_A,
        PART_B,
        *relatives(9, 400),
        *relatives(9, 400, group=SHORT_GROUP),
    ]
)


def test_a_short_gene_in_a_tight_group_is_a_length_candidate() -> None:
    found = screen_genome(NF54, ("gene_length",), [SHORT], GROUPS)
    assert found == [
        Candidate(
            genome=NF54,
            target=SingleGeneTarget(check="gene_length", genes=("NF54_SHORT",)),
        )
    ]


def test_two_short_neighbours_of_one_group_are_a_split_candidate() -> None:
    found = screen_genome(NF54, ("gene_split",), [PART_A, PART_B], GROUPS)
    assert found == [
        Candidate(
            genome=NF54,
            target=GenePairTarget(check="gene_split", genes=("NF54_A", "NF54_B")),
        )
    ]


def test_a_pair_yields_only_its_split_candidate() -> None:
    rows = [SHORT, PART_A, PART_B]
    both = screen_genome(NF54, ("gene_length", "gene_split"), rows, GROUPS)
    lengths_only = screen_genome(NF54, ("gene_length",), rows, GROUPS)
    assert [c.target.key for c in both] == [
        "gene_split:NF54_A+NF54_B",
        "gene_length:NF54_SHORT",
    ]
    assert [c.target.key for c in lengths_only] == ["gene_length:NF54_SHORT"]


def _group(*rows: GeneRow) -> list[GroupMember]:
    return [GroupMember.of_row(row) for row in rows]


def test_a_screen_group_counts_no_pseudogene_row() -> None:
    kin = [
        row.model_copy(update={"pseudo": True})
        for row in relatives(9, 400, group=SHORT_GROUP)
    ]
    groups = ortholog_groups([SHORT, *kin])
    assert [m.protein_length for m in groups[SHORT_GROUP]] == [200, *[None] * 9]
    assert screen_genome(NF54, ("gene_length",), [SHORT], groups) == []


def test_a_typical_gene_is_not_a_candidate() -> None:
    typical = gene_row("NF54_TYPICAL", NF54, 390, group=SHORT_GROUP, sequence="chr2")
    groups = ortholog_groups([typical, *relatives(9, 400, group=SHORT_GROUP)])
    assert screen_genome(NF54, ("gene_length",), [typical], groups) == []


def test_a_group_of_six_organisms_cannot_judge() -> None:
    small = ortholog_groups([SHORT, *relatives(5, 400, group=SHORT_GROUP)])
    assert screen_genome(NF54, ("gene_length",), [SHORT], small) == []


def test_a_pseudogene_and_an_ungrouped_gene_are_not_screened() -> None:
    pseudo = gene_row(
        "NF54_PSEUDO", NF54, 200, group=SHORT_GROUP, sequence="chr3", pseudo=True
    )
    loose = gene_row("NF54_LOOSE", NF54, 200, group="", sequence="chr4")
    assert screen_genome(NF54, ("gene_length",), [pseudo, loose], GROUPS) == []
    assert screen_genome(NF54, ("gene_split",), [pseudo, loose], GROUPS) == []


def test_neighbours_pair_only_within_one_group_on_one_strand_of_one_sequence() -> None:
    other_strand = gene_row("NF54_C", NF54, 210, start=12000, strand="-")
    other_sequence = gene_row("NF54_D", NF54, 210, sequence="chr5", start=13000)
    far = gene_row("NF54_F", NF54, 210, start=40000)
    assert split_pairs([PART_A, other_strand]) == []
    assert split_pairs([PART_A, other_sequence]) == []
    assert split_pairs([PART_A, far]) == []
    assert split_pairs([PART_B, PART_A]) == [(PART_A, PART_B)]


def test_a_pair_lies_at_most_the_library_gap_apart() -> None:
    edge = gene_row("NF54_E", NF54, 210, start=10599 + 20000)
    past = gene_row("NF54_P", NF54, 210, start=10599 + 20001)
    assert split_pairs([PART_A, edge]) == [(PART_A, edge)]
    assert split_pairs([PART_A, past]) == []


def test_a_gene_between_the_halves_from_another_group_does_not_break_the_pair() -> None:
    between = gene_row("NF54_X", NF54, 300, group=SHORT_GROUP, start=10700)
    assert split_pairs([PART_A, between, PART_B]) == [(PART_A, PART_B)]


def test_a_member_with_no_protein_length_does_not_break_the_pair() -> None:
    unmeasured = gene_row("NF54_N", NF54, None, start=10700)
    assert split_pairs([PART_A, unmeasured, PART_B]) == [(PART_A, PART_B)]


def test_members_of_two_genomes_never_pair() -> None:
    other = gene_row("P3D7_B", P3D7, 210, start=11000)
    assert split_pairs([PART_A, other]) == []


def test_only_the_audited_genomes_are_screened_against_the_comparison_rows() -> None:
    comparison = relatives(9, 400, group=SHORT_GROUP)
    found = screen_genomes(("gene_length",), {NF54: [SHORT]}, comparison)
    assert [c.target.key for c in found] == ["gene_length:NF54_SHORT"]
    assert audited_groups({NF54: [SHORT, PART_A]}) == frozenset(
        {SHORT_GROUP, "OG7_0000001"}
    )


def test_a_long_gene_is_never_a_length_candidate() -> None:
    long = gene_row("NF54_LONG", NF54, 700, group=SHORT_GROUP, sequence="chr2")
    groups = ortholog_groups([long, *relatives(9, 400, group=SHORT_GROUP)])
    assert screen_genome(NF54, ("gene_length",), [long], groups) == []


def test_three_coding_members_in_one_genome_yield_no_split_candidate() -> None:
    part_a = gene_row("NF54_A", NF54, 160, start=10000)
    part_b = gene_row("NF54_B", NF54, 170, start=11000)
    part_c = gene_row("NF54_C", NF54, 160, start=12000)
    rows = [part_a, part_b, part_c]
    groups = ortholog_groups([*rows, *relatives(9, 400)])
    assert split_pairs(rows) == []
    assert screen_genome(NF54, ("gene_split", "gene_length"), rows, groups) == []


def test_the_library_judges_a_split_only_with_exactly_two_coding_members() -> None:
    part_a = gene_row("NF54_A", NF54, 160, start=10000)
    part_b = gene_row("NF54_B", NF54, 170, start=11000)
    third = gene_row("NF54_C", NF54, 160, start=12000)
    pseudo = gene_row("NF54_C", NF54, 160, start=12000, pseudo=True)
    kin = relatives(9, 400)
    assert call_length([part_a, part_b], _group(part_a, part_b, *kin)).length_class == (
        "SPLIT"
    )
    assert call_length(
        [part_a, part_b], _group(part_a, part_b, pseudo, *kin)
    ).length_class == ("SPLIT")
    assert call_length(
        [part_a, part_b], _group(part_a, part_b, third, *kin)
    ).length_class == ("UNQUALIFIED")
    with pytest.raises(
        ValueError, match="a length call reads one gene or a pair, not 3"
    ):
        call_length([part_a, part_b, third], _group(part_a, part_b, third, *kin))


def test_a_pseudogene_call_pairs_with_its_reference_gene_by_product() -> None:
    family = NF54_PIGA_ROW.model_copy(
        update={"gene": "PfNF54_X:pseudogene", "product": "rifin, pseudogene"}
    )
    reference_pseudogene = P3D7_PIGA_ROW.model_copy(
        update={"gene": "PF3D7_X", "pseudo": True, "gene_type": "pseudogene"}
    )
    found = pseudogene_candidates(
        P3D7,
        [P3D7_PIGA_ROW, reference_pseudogene],
        {NF54: [NF54_PIGA_ROW, family], P3D7: [P3D7_PIGA_ROW, reference_pseudogene]},
    )
    assert found == [
        Candidate(
            genome=NF54,
            target=GenePairTarget(
                check="pseudogene_call",
                genes=(NF54_PIGA_PSEUDOGENE, "PF3D7_1032400"),
            ),
        )
    ]
    assert found[0].target.key == (
        "pseudogene_call:PfNF54_100037200%3Apseudogene+PF3D7_1032400"
    )


def test_no_pseudogene_call_pairs_without_the_reference_rows() -> None:
    assert pseudogene_candidates(P3D7, [], {NF54: [NF54_PIGA_ROW]}) == []
