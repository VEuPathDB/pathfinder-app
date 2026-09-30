"""A build outcome goes stale the moment the strategy is edited outside the
conversation.

The Lead reads cached counts from the Ledger, so without this detector it
answers "how many genes now?" with the pre-edit number and no hedge.
"""

from __future__ import annotations

from pathfinder.domain.strategy.build_outcome import BuildOutcome, BuiltCounts
from pathfinder.domain.strategy.staleness import StaleBuild, detect_build_staleness

_BUILT = BuildOutcome(pushed_step_ids=["a", "b"])


def _stale(
    held: dict[str, int | None], live: dict[str, int | None]
) -> StaleBuild | None:
    """The staleness of a build whose session holds ``held`` against the site's ``live``."""
    return detect_build_staleness(_BUILT, BuiltCounts(by_step=held), live)


def _report(held: dict[str, int | None], live: dict[str, int | None]) -> str:
    """What the staleness reads out, empty when nothing is stale."""
    stale = _stale(held, live)
    return "" if stale is None else stale.render()


def test_no_outcome_is_not_stale() -> None:
    read = [
        detect_build_staleness(outcome, BuiltCounts(by_step={"a": 2}), {"a": 5})
        for outcome in (None, _BUILT)
    ]

    assert [None if r is None else r.changed_nodes for r in read] == [
        None,
        [("a", 2, 5)],
    ]


def test_matching_counts_are_not_stale() -> None:
    assert _report(({"a": 100, "b": 20}), {"a": 100, "b": 20}) == ""


def test_changed_count_is_stale() -> None:
    stale = _stale(({"a": 2862}), {"a": 587})
    assert stale is not None
    assert stale.changed_nodes == [("a", 2862, 587)]


def test_reports_every_changed_node() -> None:
    stale = _stale(({"a": 10, "b": 20}), {"a": 11, "b": 21})
    assert stale is not None
    assert stale.changed_nodes == [("a", 10, 11), ("b", 20, 21)]


def test_removed_node_is_stale() -> None:
    stale = _stale(({"a": 10, "b": 20}), {"a": 10})
    assert stale is not None
    assert stale.removed_nodes == ["b"]


def test_added_node_is_stale() -> None:
    stale = _stale(({"a": 10}), {"a": 10, "b": 20})
    assert stale is not None
    assert stale.added_nodes == ["b"]


def test_unknown_live_count_does_not_flag_staleness() -> None:
    # A live count we could not resolve is absence of evidence, not evidence of
    # change; flagging it would cry wolf on every WDK hiccup.
    assert _report(({"a": 10}), {"a": None}) == ""


def test_unknown_recorded_count_does_not_flag_staleness() -> None:
    assert _report(({"a": None}), {"a": 10}) == ""


def test_empty_live_counts_is_not_stale() -> None:
    # No live read available must not fabricate staleness.
    assert _report(({"a": 10}), {}) == ""


def test_render_names_the_discrepancy() -> None:
    text = _report(({"a": 2862}), {"a": 587})

    assert "2862" in text
    assert "587" in text
    assert "edited" in text.lower()
