"""Enrichment export cells for values that are unbounded or not computable.

The CSV and TSV downloads are what a reviewer reads, so an unbounded ratio must
say so and a probability that is not computable must stay blank.
"""

from __future__ import annotations

from veupathdb_mcp.wdk.enrichment import EnrichmentResult, EnrichmentTerm

from pathfinder.services.export.service import enrichment_rows


def _term(**overrides: object) -> EnrichmentTerm:
    fields: dict[str, object] = {
        "term_id": "GO:0004672",
        "term_name": "protein kinase activity",
        "gene_count": 3,
        "background_count": 120,
        "fold_enrichment": 3.48,
        "odds_ratio": 4.12,
        "p_value": 0.0001,
        "fdr": 0.002,
        "bonferroni": 0.005,
        "genes": ["PF3D7_0100100", "PF3D7_0200200"],
    }
    fields.update(overrides)
    return EnrichmentTerm.model_validate(fields)


def _results(term: EnrichmentTerm) -> list[EnrichmentResult]:
    return [EnrichmentResult(analysis_type="go_function", terms=[term])]


def test_a_finite_term_keeps_its_numbers() -> None:
    header, rows = enrichment_rows(_results(_term()))

    assert header == [
        "analysis_type",
        "term_id",
        "term_name",
        "gene_count",
        "background_count",
        "fold_enrichment",
        "odds_ratio",
        "p_value",
        "fdr",
        "bonferroni",
        "genes",
    ]
    assert rows == [
        [
            "go_function",
            "GO:0004672",
            "protein kinase activity",
            3,
            120,
            3.48,
            4.12,
            0.0001,
            0.002,
            0.005,
            "PF3D7_0100100;PF3D7_0200200",
        ]
    ]


def test_an_unbounded_ratio_exports_as_inf() -> None:
    term = _term(fold_enrichment="Infinity", odds_ratio="Infinity")

    _, [row] = enrichment_rows(_results(term))

    assert row[5] == "Inf"
    assert row[6] == "Inf"


def test_a_probability_that_is_not_computable_exports_as_a_blank_cell() -> None:
    term = _term(p_value="NaN", fdr="NaN", bonferroni="NaN")

    _, [row] = enrichment_rows(_results(term))

    assert row[7] == ""
    assert row[8] == ""
    assert row[9] == ""
