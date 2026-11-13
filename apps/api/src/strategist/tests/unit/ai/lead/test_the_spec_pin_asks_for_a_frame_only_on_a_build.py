from __future__ import annotations

import pytest

from strategist.ai.lead.intent import (
    BUILDING_INTENTS,
    IntentClassification,
    UserIntent,
)
from strategist.ai.lead.lead_pins import pinned_operational_spec
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

ASKS = "## Operational Spec\nNot framed yet. Call ``frame_problem``."
STATES = "## Operational Spec\nNot framed yet."


def _pin(classification: IntentClassification | None) -> str | None:
    state = pipeline_state("veupathdb")
    intent = (
        None
        if classification is None
        else UserIntent(classification=classification, inferred_goal="genome facts")
    )
    state.turn_markers.intent_classified = classification is not None
    return pinned_operational_spec(run_context_for(lead_deps(state, intent=intent)))


@pytest.mark.parametrize("kind", sorted(BUILDING_INTENTS))
def test_a_turn_that_asks_for_a_build_is_told_to_frame(
    kind: IntentClassification,
) -> None:
    assert _pin(kind) == ASKS


@pytest.mark.parametrize(
    "kind",
    [
        IntentClassification.FOLLOW_UP_QUESTION,
        IntentClassification.CONTEXT_STATEMENT,
        IntentClassification.DENIAL,
    ],
)
def test_a_turn_that_asks_for_no_build_is_only_told_nothing_is_framed(
    kind: IntentClassification,
) -> None:
    assert _pin(kind) == STATES


def test_an_unread_turn_is_told_to_frame() -> None:
    assert _pin(None) == ASKS
