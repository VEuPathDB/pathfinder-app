"""The separation arc: the run on the controls the message pastes, its card, the build a
yes starts, and the check of the adopted strategy with those controls.

The Lead's reply restates no count: the facts part beside it shows each built
step with its count.
"""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic import Field
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.lead_flow import FACTS_BESIDE
from pathfinder.ai.models.mock.message_words import turn_controls
from pathfinder.ai.models.mock.reads import (
    ToolAnswer,
    last_return,
    refusal_of,
    text_return,
)
from pathfinder.domain.separation import SEPARATION_BUDGET_MIN

_RUN = "separate_controls"
_ADOPT = "adopt_separating_strategy"
_ADOPT_REPLY = "[mock] The separation found a strategy; the card offers to build it."
_NOT_RUN = "The separation run did not start, so I have no strategy to offer."


class _Report(ToolAnswer):
    task_id: str = ""


class _Resumed(ToolAnswer):
    """A durable call's answer, as the model reads it."""

    result: _Report = Field(default_factory=_Report)


_BUILT = (
    "I built the strategy the separation run measured, and the check tested it "
    "with the controls it was measured on."
)
RUN_REPLY = (
    "[mock] I will measure your positive and negative controls against the "
    "site's searches."
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
                "reply": RUN_REPLY,
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
        lead_final(f"{_BUILT}{FACTS_BESIDE}", "complete", strategy_changed=True),
    ]
