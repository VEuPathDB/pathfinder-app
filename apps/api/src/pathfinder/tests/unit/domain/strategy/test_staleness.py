"""A build outcome goes stale the moment the strategy is edited outside the
conversation.

The Lead reads cached counts from the Ledger, so without this detector it
answers "how many genes now?" with the pre-edit number and no hedge.
"""

from __future__ import annotations

from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.staleness import detect_build_staleness


def _outcome(counts: dict[str, int | None], root: int | None = None) -> BuildOutcome:
    return BuildOutcome(
        node_results=[
            NodeResult(node_id=nid, search_name="GenesByTaxon", count=c, status="ok")
            for nid, c in counts.items()
        ],
        root_count=root,
    )


def _report(outcome: BuildOutcome | None, live: dict[str, int | None]) -> str:
    """What the staleness reads out, empty when nothing is stale."""
    stale = detect_build_staleness(outcome, live)
    return "" if stale is None else stale.render()


def test_no_outcome_is_not_stale() -> None:
    assert _report(None, {"a": 5}) == ""


def test_matching_counts_are_not_stale() -> None:
    assert _report(_outcome({"a": 100, "b": 20}), {"a": 100, "b": 20}) == ""


def test_changed_count_is_stale() -> None:
    stale = detect_build_staleness(_outcome({"a": 2862}), {"a": 587})
    assert stale is not None
    assert stale.changed_nodes == [("a", 2862, 587)]


def test_reports_every_changed_node() -> None:
    stale = detect_build_staleness(_outcome({"a": 10, "b": 20}), {"a": 11, "b": 21})
    assert stale is not None
    assert stale.changed_nodes == [("a", 10, 11), ("b", 20, 21)]


def test_removed_node_is_stale() -> None:
    stale = detect_build_staleness(_outcome({"a": 10, "b": 20}), {"a": 10})
    assert stale is not None
    assert stale.removed_nodes == ["b"]


def test_added_node_is_stale() -> None:
    stale = detect_build_staleness(_outcome({"a": 10}), {"a": 10, "b": 20})
    assert stale is not None
    assert stale.added_nodes == ["b"]


def test_unknown_live_count_does_not_flag_staleness() -> None:
    # A live count we could not resolve is absence of evidence, not evidence of
    # change; flagging it would cry wolf on every WDK hiccup.
    assert _report(_outcome({"a": 10}), {"a": None}) == ""


def test_unknown_recorded_count_does_not_flag_staleness() -> None:
    assert _report(_outcome({"a": None}), {"a": 10}) == ""


def test_empty_live_counts_is_not_stale() -> None:
    # No live read available must not fabricate staleness.
    assert _report(_outcome({"a": 10}), {}) == ""


def test_render_names_the_discrepancy() -> None:
    text = _report(_outcome({"a": 2862}), {"a": 587})

    assert "2862" in text
    assert "587" in text
    assert "edited" in text.lower()
