"""A volcano direction is stated by the labels of the group it keeps."""

from __future__ import annotations

from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.services.eda.direction import (
    direction_sentence,
    selection_sentence,
    sign_sentence,
)

PBM = EdaComparison(group_a=["24h pbm"], group_b=["18h pbm", "36h pbm"])


def test_up_only_keeps_the_genes_higher_in_group_b() -> None:
    assert direction_sentence(PBM, "upOnly") == (
        "Genes higher in 18h pbm, 36h pbm than in 24h pbm"
    )


def test_down_only_keeps_the_genes_higher_in_group_a() -> None:
    assert direction_sentence(PBM, "downOnly") == (
        "Genes higher in 24h pbm than in 18h pbm, 36h pbm"
    )


def test_up_and_down_keeps_the_genes_that_differ() -> None:
    assert direction_sentence(PBM, "upAndDown") == (
        "Genes that differ between 24h pbm and 18h pbm, 36h pbm"
    )


def test_the_sign_sentence_names_both_groups() -> None:
    assert sign_sentence(PBM) == (
        "A positive effect size means the gene is higher in group B "
        "(18h pbm, 36h pbm) than in group A (24h pbm)."
    )


def test_the_selection_names_the_count_and_the_kept_group() -> None:
    assert selection_sentence(PBM, "upOnly", count=363) == (
        "Kept 363 genes higher in 18h pbm, 36h pbm than in 24h pbm."
    )


def test_a_selection_with_no_count_names_the_kept_group() -> None:
    assert selection_sentence(PBM, "downOnly", count=None) == (
        "Keeps the genes higher in 24h pbm than in 18h pbm, 36h pbm."
    )
