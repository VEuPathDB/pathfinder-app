from __future__ import annotations

import pytest

from pathfinder.domain.eda_cut import (
    ClassCount,
    NumericBin,
    TailEdge,
    cut_question,
    tail_edge,
    tail_edges,
)
from pathfinder.domain.strategy.question_options import TailRule


def _bins(counts: list[int], *, start: float = -5.0) -> list[NumericBin]:
    return [
        NumericBin(bin_start=start + i, bin_end=start + i + 1, value=count)
        for i, count in enumerate(counts)
    ]


_SPREAD = _bins([3, 4, 5, 8, 30, 30, 8, 5, 4, 3])


@pytest.mark.parametrize(
    ("rule", "bound", "count"),
    [
        (TailRule(end="low", percent=5), -3.0, 7),
        (TailRule(end="low", percent=10), -2.0, 12),
        (TailRule(end="high", percent=5), 3.0, 7),
        (TailRule(end="high", percent=10), 2.0, 12),
    ],
)
def test_a_tail_ends_at_the_first_edge_that_reaches_its_share(
    rule: TailRule, bound: float, count: int
) -> None:
    assert tail_edge(_SPREAD, rule) == TailEdge(
        rule=rule, bound=bound, count=count, total=100
    )


def test_a_tail_label_states_the_share_reached_the_bound_and_the_count() -> None:
    low = tail_edge(_SPREAD, TailRule(end="low", percent=5))
    high = tail_edge(_SPREAD, TailRule(end="high", percent=10))
    assert low is not None
    assert high is not None
    assert (
        low.label("Fitness score", "genes"),
        high.label("Fitness score", "genes"),
    ) == (
        "Lowest 7.0% of Fitness score: at most -3 (7 genes)",
        "Highest 12.0% of Fitness score: at least 2 (12 genes)",
    )


def test_one_bin_over_the_share_holds_the_whole_tail() -> None:
    bins = _bins([60, 20, 20], start=0.0)
    assert [(e.rule, e.bound, e.count) for e in tail_edges(bins)] == [
        (TailRule(end="low", percent=5), 1.0, 60),
        (TailRule(end="high", percent=5), 2.0, 20),
    ]


def test_an_empty_distribution_offers_no_tail() -> None:
    assert (tail_edges([]), tail_edges(_bins([0, 0, 0]))) == ([], [])


def test_a_tail_that_holds_every_record_is_no_cut() -> None:
    assert tail_edges(_bins([10], start=0.0)) == []


def test_a_bound_is_held_as_its_label_writes_it() -> None:
    bins = [
        NumericBin(bin_start=-2.5100000000000002, bin_end=-2.3100000000000005, value=5),
        NumericBin(bin_start=-2.3100000000000005, bin_end=0.0, value=95),
    ]
    edge = tail_edge(bins, TailRule(end="low", percent=5))
    assert edge is not None
    assert edge.bound == -2.31


def test_the_cut_question_offers_the_tails_then_the_classes() -> None:
    tails = tail_edges(_SPREAD)
    classes = [
        ClassCount(
            entity_id="E", variable_id="V", variable_name="Phenotype", value=v, count=n
        )
        for v, n in (("Essential", 412), ("Dispensable", 1830))
    ]
    question = cut_question("Fitness score", "genes", tails, classes)
    assert [o.label for o in question.options] == [
        "Lowest 7.0% of Fitness score: at most -3 (7 genes)",
        "Lowest 12.0% of Fitness score: at most -2 (12 genes)",
        "Highest 7.0% of Fitness score: at least 3 (7 genes)",
        "Highest 12.0% of Fitness score: at least 2 (12 genes)",
        "Phenotype: Essential (412 genes)",
        "Phenotype: Dispensable (1830 genes)",
    ]


def test_the_cut_question_holds_eight_options_at_most() -> None:
    classes = [
        ClassCount(
            entity_id="E", variable_id="V", variable_name="Class", value=str(v), count=1
        )
        for v in range(8)
    ]
    question = cut_question("Fitness score", "genes", tail_edges(_SPREAD), classes)
    assert len(question.options) == 8
