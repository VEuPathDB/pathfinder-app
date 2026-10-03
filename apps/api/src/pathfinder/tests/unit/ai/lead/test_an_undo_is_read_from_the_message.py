"""The intent records an undo when the classifier states one or the message asks for one."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)


async def _classified(message: str, *, undo: bool) -> LeadDeps:
    state = pipeline_state(user_prompt=message)
    state.user_message_id = uuid4()
    deps = lead_deps(state, strategy_session=session_with_one_step())
    await classify_user_intent(
        run_context_for(deps, "t_classify"),
        UserIntent(
            classification=IntentClassification.EDIT_STRATEGY,
            inferred_goal="restore the strategy",
            undo=undo,
        ),
    )
    return deps


@pytest.mark.parametrize(
    ("message", "classifier_undo", "recorded"),
    [
        ("Undo that, keep the intersection.", False, True),
        ("Take that change away again.", True, True),
        ("flip the last combine to a UNION", False, False),
    ],
)
async def test_the_recorded_undo_is_the_classifier_s_or_the_message_s(
    message: str, classifier_undo: bool, recorded: bool
) -> None:
    deps = await _classified(message, undo=classifier_undo)

    assert deps.intent is not None
    assert deps.intent.undo is recorded
