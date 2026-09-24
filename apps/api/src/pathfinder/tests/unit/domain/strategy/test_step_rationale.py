"""Why a step runs its search: the label, the line, and where a reply gives it."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.step_rationale import (
    AnalysisRationale,
    ComparedSearch,
    RationaleBasis,
    SearchRationale,
    StepRationale,
    names_the_phrase,
    said_beside,
)
from pathfinder.tests.unit.domain.strategy._analysis import DATASET, WORDS, binding

_OVER = [
    ComparedSearch(
        name="GenesByText", display_name="Gene Text Search", similarity=0.41
    ),
    ComparedSearch(
        name="GenesBySignalP", display_name="Signal Peptide", similarity=None
    ),
]


def _chosen(basis: RationaleBasis, term: str, **fields: object) -> SearchRationale:
    return SearchRationale.model_validate(
        {
            "search_name": "GenesByExportPred",
            "basis": basis,
            "term": term,
            "reason": f"no search states it; {term} is the closest",
            "tool_call_id": "call_1",
            **fields,
        }
    )


@pytest.mark.parametrize(
    ("basis", "term", "short"),
    [
        ("parameter", "Percentile", "sets Percentile"),
        ("organism", "Plasmodium falciparum 3D7", "covers Plasmodium falciparum 3D7"),
        ("record_type", "transcript", "returns transcript"),
        ("only_match", "exported", "only search naming exported"),
        ("nearest", "GPI anchor", "nearest to GPI anchor"),
    ],
)
def test_each_basis_has_its_label(basis: RationaleBasis, term: str, short: str) -> None:
    assert _chosen(basis, term).short == short


def test_the_line_names_what_the_search_was_chosen_over() -> None:
    chosen = _chosen("nearest", "GPI anchor", compared=_OVER)

    assert chosen.line() == (
        "no search states it; GPI anchor is the closest "
        "(over Gene Text Search 0.41, Signal Peptide)"
    )


def test_a_line_with_nothing_compared_is_the_reason() -> None:
    assert _chosen("parameter", "Organism").line() == (
        "no search states it; Organism is the closest"
    )


def test_the_label_is_served_and_derived_again_on_the_way_back() -> None:
    chosen = _chosen("nearest", "GPI anchor", compared=_OVER, sources=["PMID:123"])
    dumped = chosen.model_dump(by_alias=True, mode="json")
    stale = dumped | {"short": "a label another release wrote"}

    assert (dumped["short"], SearchRationale.model_validate(stale)) == (
        "nearest to GPI anchor",
        chosen,
    )


def test_a_computed_analysis_is_held_to_its_method() -> None:
    reason = AnalysisRationale.of(binding())

    assert (reason.dataset_id, reason.term, reason.reason, reason.short) == (
        DATASET,
        "DESeq",
        WORDS,
        "computed by DESeq",
    )


def test_a_subset_is_held_to_its_first_filter() -> None:
    subset = AnalysisBinding(
        dataset_id=DATASET,
        subset=["Age >= 5", "Country = Mali"],
        words="The subset: Age >= 5, Country = Mali",
    )
    reason = AnalysisRationale.of(subset)

    assert (reason.method, reason.term, reason.short) == (
        None,
        "Age >= 5",
        "analysis subset",
    )


def test_the_kind_picks_the_rationale() -> None:
    adapter: TypeAdapter[StepRationale] = TypeAdapter(StepRationale)
    served = AnalysisRationale.of(binding()).model_dump(by_alias=True, mode="json")

    assert adapter.validate_python(served) == AnalysisRationale.of(binding())


def test_a_phrase_is_named_whole_in_any_case() -> None:
    assert (
        names_the_phrase("I used exported protein here.", "Exported Protein"),
        names_the_phrase("Exported Proteins", "Exported Protein"),
    ) == (True, False)


def test_a_term_in_the_same_paragraph_is_beside_the_name() -> None:
    prose = "Exported Protein is the nearest to a GPI anchor on PlasmoDB."

    assert said_beside(prose, "Exported Protein", "GPI anchor") is True


def test_a_term_across_a_blank_line_is_not_beside_the_name() -> None:
    prose = "I used Exported Protein.\n\nNo search states a GPI anchor."

    assert said_beside(prose, "Exported Protein", "GPI anchor") is False


def test_a_term_inside_one_list_item_is_beside_the_name() -> None:
    prose = (
        "The steps:\n- Exported Protein, nearest to a GPI anchor\n- Orthologs, mapped"
    )

    assert said_beside(prose, "Exported Protein", "GPI anchor") is True


def test_a_term_in_the_next_list_item_is_not_beside_the_name() -> None:
    prose = "The steps:\n- Exported Protein\n- GPI anchor is what it stands for"

    assert said_beside(prose, "Exported Protein", "GPI anchor") is False


def test_a_term_in_a_sub_bullet_of_the_item_is_beside_the_name() -> None:
    prose = "- Exported Protein\n  - nearest to a GPI anchor"

    assert said_beside(prose, "Exported Protein", "GPI anchor") is True


def test_an_indented_continuation_line_belongs_to_the_item_above() -> None:
    prose = "- Exported Protein, the closest search\n  to a GPI anchor\n- Orthologs"

    assert said_beside(prose, "Exported Protein", "GPI anchor") is True


def test_a_term_in_the_sub_bullet_of_the_next_item_is_not_beside_the_name() -> None:
    prose = "- Exported Protein\n- Orthologs\n  - nearest to a GPI anchor"

    assert said_beside(prose, "Exported Protein", "GPI anchor") is False
