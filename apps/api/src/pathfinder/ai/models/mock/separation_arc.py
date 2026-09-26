"""The separation arc: the run on the controls the message pastes, its card, the build a
yes starts, and the check of the adopted strategy with those controls.

The Lead's reply names each built search beside the count its step returned,
read from the build's own record, never typed in here.
"""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic import Field
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.message_words import turn_controls
from pathfinder.ai.models.mock.reads import (
    ToolAnswer,
    added_searches,
    last_return,
    refusal_of,
    text_return,
)
from pathfinder.domain.separation import SEPARATION_BUDGET_MIN

_RUN = "separate_controls"
_ADOPT = "adopt_separating_strategy"
# The reply each card call of the arc carries.
_RUN_REPLY = "[mock] I will measure the seed's two lists against the site's searches."
_ADOPT_REPLY = "[mock] The separation found a strategy; the card offers to build it."
_NOT_RUN = "The separation run did not start, so I have no strategy to offer."


class _Report(ToolAnswer):
    task_id: str = ""


class _Resumed(ToolAnswer):
    """A durable call's answer, as the model reads it."""

    result: _Report = Field(default_factory=_Report)


def _built_prose(messages: list[ModelMessage]) -> str:
    lines = [
        f"- {added.search_display_name}, which alone returns {added.rationale.term}"
        for added in added_searches(messages, _ADOPT)
        if added.rationale is not None
    ]
    return "\n".join(
        [
            "I built the strategy the separation run measured. It runs:",
            *lines,
            "",
            "The check tested it with the controls it was measured on.",
        ]
    )


def separation(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Run the separation, offer its strategy, build it on a yes, and verify it."""
    positives, negatives = turn_controls()
    report = (last_return(messages, _RUN, _Resumed) or _Resumed()).result
    head = [
        classify("new_strategy"),
        scripted_call(
            _RUN,
            {
                "positive_controls": positives,
                "negative_controls": negatives,
                "mode": "exact",
                "budget": SEPARATION_BUDGET_MIN,
                "reply": _RUN_REPLY,
            },
        ),
    ]
    answered = text_return(messages, _RUN) or refusal_of(messages, _RUN)
    if answered is not None and not report.task_id:
        return [*head, lead_final(_NOT_RUN, "await_user")]
    return [
        *head,
        scripted_call(_ADOPT, {"task_id": report.task_id, "reply": _ADOPT_REPLY}),
        scripted_call("verify_strategy", {"reason": "check the adopted strategy"}),
        lead_final(_built_prose(messages), "complete", strategy_changed=True),
    ]
