"""The evidence card carries the facts of a check and no verdict: the study steps
the site did not describe are a fact of the site, listed as pending."""

from __future__ import annotations

from datetime import UTC, datetime

from pathfinder.ai.lead.evidence_card import CardSources, assemble_evidence_card
from pathfinder.domain.evidence import VerificationReview
from pathfinder.domain.strategy.build_outcome import BuiltCounts

_SOURCES = CardSources(
    check_id="call_verify",
    revision="rev-1",
    site_id="plasmodb",
    labels={},
    live_wdk_step_ids=frozenset(),
    wdk_strategy_id=None,
    root_wdk_step_id=None,
    node_results=[],
    counts=BuiltCounts(),
    spec=None,
    control_tests=[],
    pending_checks=["Febrile vs normal"],
    review=VerificationReview(),
)


def test_the_card_lists_the_pending_steps_and_no_verdict() -> None:
    card = assemble_evidence_card(
        _SOURCES, None, checked_at=datetime(2026, 9, 26, 9, 0, tzinfo=UTC)
    )
    wire = card.model_dump(by_alias=True, mode="json")

    assert (wire["pendingChecks"], "verdict" in wire) == (["Febrile vs normal"], False)
    assert card.texts() == ["Febrile vs normal"]
