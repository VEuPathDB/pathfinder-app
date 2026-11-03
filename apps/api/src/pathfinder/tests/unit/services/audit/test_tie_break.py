"""The relatives' lengths a confirmed length error is weighed against."""

from __future__ import annotations

from veupathdb_mcp.audit import GeneRow, GroupMember, strain_relatives, tie_break

from pathfinder.domain.audit.findings import RelativesEvidence
from pathfinder.domain.audit.length_facts import _NO_RELATIVES
from pathfinder.services.audit.tie_break import relatives_evidence
from pathfinder.services.audit.units import UnitFailure
from pathfinder.tests._support.audit import gene_row


def _weighed(
    reference: str, genes: list[str], rows: list[GeneRow]
) -> RelativesEvidence | UnitFailure:
    return relatives_evidence(
        reference, genes, rows, [GroupMember.of_row(row) for row in rows]
    )


ROWS = [
    gene_row("REF", "Plasmodium falciparum 3D7", 319),
    gene_row("STRAIN", "Plasmodium falciparum Dd2", 110),
    gene_row("PV", "Plasmodium vivax P01", 300),
    gene_row("PK", "Plasmodium knowlesi H", 302),
    gene_row("PB", "Plasmodium berghei ANKA", 298),
]
RELATIVES = {
    "Plasmodium vivax P01": 300,
    "Plasmodium knowlesi H": 302,
    "Plasmodium berghei ANKA": 298,
}


ONE_IN_EACH_TIER = [
    *ROWS[:3],
    gene_row("TG", "Toxoplasma gondii ME49", 350),
]


def test_one_relative_in_each_tier_is_too_few() -> None:
    weighed = _weighed("REF", ["STRAIN"], ONE_IN_EACH_TIER)
    assert isinstance(weighed, RelativesEvidence)
    assert (weighed.relative_lengths, weighed.reference_organism) == (
        {},
        "Plasmodium falciparum 3D7",
    )
    reference, strain, *_ = ONE_IN_EACH_TIER
    found = strain_relatives(
        reference, strain, [GroupMember.of_row(row) for row in ONE_IN_EACH_TIER]
    )
    assert found.missing == "FEWER_THAN_TWO"
    assert _NO_RELATIVES[found.missing] == (
        "fewer than two genomes of other species in this genus, and fewer than two "
        "in other genera, have a length for the gene"
    )


def test_a_gene_held_only_by_the_reference_species_is_too_few() -> None:
    rows = [
        gene_row("ME49", "Toxoplasma gondii ME49", 319),
        gene_row("GT1", "Toxoplasma gondii GT1", 110),
        gene_row("VEG", "Toxoplasma gondii VEG", 300),
        gene_row("RH", "Toxoplasma gondii RH", 302),
        gene_row("P89", "Toxoplasma gondii P89", 298),
    ]
    weighed = _weighed("ME49", ["GT1"], rows)
    assert isinstance(weighed, RelativesEvidence)
    assert weighed.relative_lengths == {}
    assert weighed.reference_organism == "Toxoplasma gondii ME49"
    found = strain_relatives(
        rows[0], rows[1], [GroupMember.of_row(row) for row in rows]
    )
    assert found.missing == "FEWER_THAN_TWO"
    assert found.members == []
    assert _NO_RELATIVES[found.missing] == (
        "fewer than two genomes of other species in this genus, and fewer than two "
        "in other genera, have a length for the gene"
    )


def test_a_reference_row_with_no_length_still_names_its_organism() -> None:
    rows = [gene_row("REF", "Plasmodium falciparum 3D7", None), *ONE_IN_EACH_TIER[1:]]
    weighed = _weighed("REF", ["STRAIN"], rows)
    assert isinstance(weighed, RelativesEvidence)
    assert (
        weighed.reference_length,
        weighed.reference_organism,
        weighed.relative_lengths,
    ) == (None, "Plasmodium falciparum 3D7", {})


def test_an_absent_reference_row_names_no_organism() -> None:
    weighed = _weighed("REF", ["STRAIN"], ONE_IN_EACH_TIER[1:])
    assert isinstance(weighed, RelativesEvidence)
    assert (
        weighed.reference_length,
        weighed.reference_organism,
        weighed.relative_lengths,
    ) == (None, None, {})


def test_the_relatives_are_the_other_species_of_the_reference_genus() -> None:
    assert tie_break(319, 110, 300.0) == "STRAIN_SHORT"
    assert _weighed("REF", ["STRAIN"], ROWS) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=110,
        relatives_median=300.0,
        relative_lengths=RELATIVES,
        relatives_tier="SAME_GENUS",
        side=tie_break(319, 110, 300.0),
        reference_organism="Plasmodium falciparum 3D7",
    )


def test_a_model_the_relatives_support_leaves_the_side_unclear() -> None:
    rows = [*ROWS[:1], gene_row("STRAIN", "Plasmodium falciparum Dd2", 296), *ROWS[2:]]
    assert tie_break(319, 296, 300.0) == "UNCLEAR"
    assert _weighed("REF", ["STRAIN"], rows) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=296,
        relatives_median=300.0,
        relative_lengths=RELATIVES,
        relatives_tier="SAME_GENUS",
        side="UNCLEAR",
        reference_organism="Plasmodium falciparum 3D7",
    )


def test_a_split_pair_is_weighed_by_its_parts_together() -> None:
    rows = [*ROWS, gene_row("STRAIN2", "Plasmodium falciparum Dd2", 190)]
    assert _weighed("REF", ["STRAIN", "STRAIN2"], rows) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=300,
        relatives_median=300.0,
        relative_lengths=RELATIVES,
        relatives_tier="SAME_GENUS",
        side="UNCLEAR",
        reference_organism="Plasmodium falciparum 3D7",
    )


def test_a_model_with_a_part_of_no_length_has_no_model_length() -> None:
    rows = [*ROWS, gene_row("STRAIN2", "Plasmodium falciparum Dd2", None)]
    assert _weighed("REF", ["STRAIN", "STRAIN2"], rows) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=None,
        relatives_median=300.0,
        relative_lengths=RELATIVES,
        relatives_tier="SAME_GENUS",
        reference_organism="Plasmodium falciparum 3D7",
        side=None,
    )


def test_a_model_part_the_rows_do_not_hold_has_no_model_length() -> None:
    assert _weighed("REF", ["STRAIN", "GONE"], ROWS) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=None,
        relatives_median=300.0,
        relative_lengths=RELATIVES,
        relatives_tier="SAME_GENUS",
        reference_organism="Plasmodium falciparum 3D7",
        side=None,
    )


def test_a_reference_the_rows_do_not_hold_has_no_lengths() -> None:
    assert _weighed("GONE", ["STRAIN"], ROWS) == RelativesEvidence(
        reference_gene="GONE",
        reference_length=None,
        model_length=110,
        relatives_median=None,
        relative_lengths={},
        relatives_tier=None,
        side=None,
        reference_organism=None,
    )


def test_too_few_relatives_store_no_lengths() -> None:
    assert _weighed("REF", ["STRAIN"], ROWS[:3]) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=110,
        relatives_median=None,
        relative_lengths={},
        side="NO_RELATIVES",
        reference_organism="Plasmodium falciparum 3D7",
        relatives_tier=None,
    )


def test_a_model_the_rows_do_not_hold_is_a_failed_unit() -> None:
    assert _weighed("REF", ["GONE", "GONE2"], ROWS) == UnitFailure(
        status="failed", message="the record reads of GONE hold no row of the model"
    )


def test_the_models_own_organism_has_no_vote_among_the_relatives() -> None:
    rows = [
        gene_row("PVX_REF", "Plasmodium vivax P01", 319),
        gene_row("PKNH_MODEL", "Plasmodium knowlesi H", 110),
        gene_row("PF3D7_X", "Plasmodium falciparum 3D7", 300),
        gene_row("TG_A", "Toxoplasma gondii ME49", 310),
        gene_row("CP_A", "Cryptosporidium parvum Iowa II", 312),
    ]
    assert _weighed("PVX_REF", ["PKNH_MODEL"], rows) == RelativesEvidence(
        reference_gene="PVX_REF",
        reference_length=319,
        model_length=110,
        relatives_median=311.0,
        relative_lengths={
            "Toxoplasma gondii ME49": 310,
            "Cryptosporidium parvum Iowa II": 312,
        },
        relatives_tier="OTHER_GENERA",
        side="STRAIN_SHORT",
        reference_organism="Plasmodium vivax P01",
    )


def test_the_lengths_are_the_records_and_the_median_is_the_groups() -> None:
    group = [GroupMember.of_row(row) for row in ROWS[2:]]
    assert relatives_evidence("REF", ["STRAIN"], ROWS[:2], group) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=110,
        relatives_median=300.0,
        relative_lengths=RELATIVES,
        relatives_tier="SAME_GENUS",
        side="STRAIN_SHORT",
        reference_organism="Plasmodium falciparum 3D7",
    )
