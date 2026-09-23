"""A volcano direction is stated by the labels of the group it keeps."""

from __future__ import annotations

from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.services.eda.direction import (
    caption_verdict,
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


HIGH_LOW = EdaComparison(group_a=["high"], group_b=["low"])
LETTERS = EdaComparison(group_a=["A"], group_b=["B"])


def test_a_caption_that_names_only_the_other_group_disagrees() -> None:
    assert (
        caption_verdict("Genes higher in 24h pbm", PBM, "upOnly")
        == "names_the_other_group"
    )


def test_a_caption_whose_first_label_is_the_other_group_disagrees() -> None:
    assert (
        caption_verdict(
            "Genes higher in 24h pbm than in 18h pbm or 36h pbm", PBM, "upOnly"
        )
        == "names_the_other_group"
    )


def test_a_caption_that_names_no_label_names_no_group() -> None:
    assert (
        caption_verdict(
            "Genes expressed higher at 24 hours than at 18 or 36 hours",
            PBM,
            "downOnly",
        )
        == "names_no_group"
    )


def test_a_caption_that_leads_with_the_kept_group_agrees() -> None:
    assert (
        caption_verdict("Genes higher in 36H PBM than in 24h pbm", PBM, "upOnly")
        == "agrees"
    )


def test_a_label_inside_a_longer_word_is_not_named() -> None:
    """The "high" in "higher" is not the label high."""
    caption = "Genes higher in low than in high"
    assert caption_verdict(caption, HIGH_LOW, "upOnly") == "agrees"
    assert caption_verdict(caption, HIGH_LOW, "downOnly") == "names_the_other_group"


def test_a_one_letter_label_is_named_only_as_a_word() -> None:
    """The "a" in "that" is not the label A."""
    caption = "Genes that are higher in B than in A"
    assert caption_verdict(caption, LETTERS, "upOnly") == "agrees"


def test_a_label_followed_by_a_letter_is_not_named() -> None:
    comparison = EdaComparison(group_a=["24h"], group_b=["36h"])
    assert (
        caption_verdict("Genes higher in 24hx than in 36h", comparison, "upOnly")
        == "agrees"
    )


def test_a_label_with_a_regex_metacharacter_is_named_literally() -> None:
    comparison = EdaComparison(group_a=["control"], group_b=["IL-6 (x2)"])
    assert (
        caption_verdict(
            "Genes higher in IL-6 (x2) than in control", comparison, "upOnly"
        )
        == "agrees"
    )
    assert (
        caption_verdict("Genes higher in IL-6 x2 than in control", comparison, "upOnly")
        == "names_the_other_group"
    )


def test_the_longest_label_at_one_place_is_the_one_named() -> None:
    comparison = EdaComparison(group_a=["24h"], group_b=["24h pbm"])
    assert (
        caption_verdict("Genes higher in 24h pbm than in 24h", comparison, "upOnly")
        == "agrees"
    )


def test_a_caption_on_both_sides_always_agrees() -> None:
    assert caption_verdict("Anything at all", PBM, "upAndDown") == "agrees"
