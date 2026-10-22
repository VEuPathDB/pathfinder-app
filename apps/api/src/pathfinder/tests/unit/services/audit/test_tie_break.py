"""The relatives' lengths a confirmed length error is weighed against."""

from __future__ import annotations

from veupathdb_mcp.audit import tie_break

from pathfinder.domain.audit.findings import RelativesEvidence
from pathfinder.services.audit.checks import UnitFailure
from pathfinder.services.audit.tie_break import relatives_evidence
from pathfinder.tests._support.audit import gene_row

ROWS = [
    gene_row("REF", "Plasmodium falciparum 3D7", 319),
    gene_row("STRAIN", "Plasmodium falciparum Dd2", 110),
    gene_row("PV", "Plasmodium vivax P01", 300),
    gene_row("PK", "Plasmodium knowlesi H", 302),
    gene_row("PB", "Plasmodium berghei ANKA", 298),
]


def test_the_relatives_are_the_other_species_of_the_reference_genus() -> None:
    assert tie_break(319, 110, 300.0) == "STRAIN_SHORT"
    assert relatives_evidence("REF", ["STRAIN"], ROWS) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=110,
        relatives_median=300.0,
        side=tie_break(319, 110, 300.0),
        reference_organism="Plasmodium falciparum 3D7",
    )


def test_a_model_the_relatives_support_leaves_the_side_unclear() -> None:
    rows = [*ROWS[:1], gene_row("STRAIN", "Plasmodium falciparum Dd2", 296), *ROWS[2:]]
    assert tie_break(319, 296, 300.0) == "UNCLEAR"
    assert relatives_evidence("REF", ["STRAIN"], rows) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=296,
        relatives_median=300.0,
        side="UNCLEAR",
        reference_organism="Plasmodium falciparum 3D7",
    )


def test_a_split_pair_is_weighed_by_its_parts_together() -> None:
    rows = [*ROWS, gene_row("STRAIN2", "Plasmodium falciparum Dd2", 190)]
    assert relatives_evidence("REF", ["STRAIN", "STRAIN2"], rows) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=300,
        relatives_median=300.0,
        side="UNCLEAR",
        reference_organism="Plasmodium falciparum 3D7",
    )


def test_a_model_with_a_part_of_no_length_has_no_model_length() -> None:
    rows = [*ROWS, gene_row("STRAIN2", "Plasmodium falciparum Dd2", None)]
    assert relatives_evidence("REF", ["STRAIN", "STRAIN2"], rows) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=None,
        relatives_median=300.0,
        reference_organism="Plasmodium falciparum 3D7",
    )


def test_a_model_part_the_rows_do_not_hold_has_no_model_length() -> None:
    assert relatives_evidence("REF", ["STRAIN", "GONE"], ROWS) == RelativesEvidence(
        reference_gene="REF",
        reference_length=319,
        model_length=None,
        relatives_median=300.0,
        reference_organism="Plasmodium falciparum 3D7",
    )


def test_a_reference_the_rows_do_not_hold_has_no_lengths() -> None:
    assert relatives_evidence("GONE", ["STRAIN"], ROWS) == RelativesEvidence(
        reference_gene="GONE",
        reference_length=None,
        model_length=110,
        relatives_median=None,
    )


def test_a_model_the_rows_do_not_hold_is_a_failed_unit() -> None:
    assert relatives_evidence("REF", ["GONE", "GONE2"], ROWS) == UnitFailure(
        status="failed", message="the ortholog rows of GONE hold no row of the model"
    )


def test_the_models_own_organism_has_no_vote_among_the_relatives() -> None:
    rows = [
        gene_row("PVX_REF", "Plasmodium vivax P01", 319),
        gene_row("PKNH_MODEL", "Plasmodium knowlesi H", 110),
        gene_row("PF3D7_X", "Plasmodium falciparum 3D7", 300),
        gene_row("TG_A", "Toxoplasma gondii ME49", 310),
        gene_row("CP_A", "Cryptosporidium parvum Iowa II", 312),
    ]
    assert relatives_evidence("PVX_REF", ["PKNH_MODEL"], rows) == RelativesEvidence(
        reference_gene="PVX_REF",
        reference_length=319,
        model_length=110,
        relatives_median=311.0,
        side="STRAIN_SHORT",
        reference_organism="Plasmodium vivax P01",
    )
