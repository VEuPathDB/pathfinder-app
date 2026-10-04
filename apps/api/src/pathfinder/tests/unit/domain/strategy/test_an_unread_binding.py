"""A binding is unread while its document holds a filter or a comparison that
no read of the study or the compute named or counted."""

from __future__ import annotations

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding, CutTallies
from pathfinder.tests.unit.domain.strategy._analysis import DATASET, binding

_TALLIES = CutTallies(
    tested=200,
    retained=33,
    retained_up=33,
    retained_down=34,
    at_any_effect=55,
    at_any_significance=49,
)


def _subset(*, shown: list[str]) -> AnalysisBinding:
    return AnalysisBinding(
        dataset_id=DATASET,
        subset=["VAR_84f17484 is one of wildtype"],
        shown_subset=shown,
        words="The genes of the analysis 'wild type'",
    )


def test_a_comparison_is_read_once_its_compute_counted_the_cut() -> None:
    assert (
        binding().unread(),
        binding().model_copy(update={"tallies": _TALLIES}).unread(),
    ) == (True, False)


def test_a_filter_is_read_once_the_study_named_it() -> None:
    assert (
        _subset(shown=[]).unread(),
        _subset(shown=["genotype is one of wildtype"]).unread(),
    ) == (True, False)


def test_a_document_with_no_filter_and_no_comparison_has_nothing_to_read() -> None:
    assert AnalysisBinding(dataset_id=DATASET, words="All genes").unread() is False
