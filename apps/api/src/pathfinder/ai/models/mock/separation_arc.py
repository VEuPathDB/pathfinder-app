"""The separation arc of the deterministic test model: the run, its card, the
build a yes starts, and the check of the adopted strategy with its controls.

The Lead's reply names each built search beside the count its step returned,
read from the build's own record, never typed in here.
"""

from __future__ import annotations

import re

from assistant_core.models.scripted import (
    has_any,
    scripted_call,
    tool_return_parts,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.history import acted_tool_names, head_work_order
from pathfinder.ai.models.mock.prose_arcs import classify, lead_final
from pathfinder.domain.separation import SEPARATION_BUDGET_MIN
from pathfinder.services.experiment.seed.catalog import get_seeds_for_site

SEPARATION_MARKERS = ("separate my controls",)
_SEED = "PF3D7 Signal Peptide Genes"
_RUN = "separate_controls"
_ADOPT = "adopt_separating_strategy"
# The reply each card call of the arc carries.
_RUN_REPLY = "[mock] I will measure the seed's two lists against the site's searches."
_ADOPT_REPLY = "[mock] The separation found a strategy; the card offers to build it."
_READ = "get_strategy"
_TEST = "run_control_tests_on_step"
_CONTROLS_LINE = re.compile(r"^(positive|negative)_controls: (.*)$", re.MULTILINE)


class _Report(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    task_id: str = Field(default="", alias="taskId")


class _Resumed(BaseModel):
    """A durable call's answer, as the model reads it.

    A compacted history carries the answer as text, which holds no task id.
    """

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    result: _Report = Field(default_factory=_Report)

    @model_validator(mode="before")
    @classmethod
    def _text_is_compacted(cls, raw: object) -> object:
        return {} if isinstance(raw, str) else raw


class _Reason(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    term: str = ""


class _Added(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    search_display_name: str
    rationale: _Reason | None = None


class _Built(BaseModel):
    """The build's record of the searches it added."""

    model_config = ConfigDict(extra="ignore", from_attributes=True)

    added_searches: list[_Added] = Field(default_factory=list)


def _returned(messages: list[ModelMessage], tool_name: str) -> object | None:
    found = [p.content for p in tool_return_parts(messages) if p.tool_name == tool_name]
    return found[-1] if found else None


def _built_prose(messages: list[ModelMessage]) -> str:
    built = _Built.model_validate(_returned(messages, _ADOPT) or {})
    lines = [
        f"- {added.search_display_name}, which alone returns {added.rationale.term}"
        for added in built.added_searches
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


def separation_sequence(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """Run the separation, offer its strategy, build it on a yes, and verify it."""
    (seed,) = [s for s in get_seeds_for_site("plasmodb") if s.name == _SEED]
    controls = seed.control_set
    report = _Resumed.model_validate(_returned(messages, _RUN) or {}).result
    return [
        classify("new_strategy"),
        scripted_call(
            _RUN,
            {
                "positive_controls": [] if controls is None else controls.positive_ids,
                "negative_controls": [] if controls is None else controls.negative_ids,
                "mode": "exact",
                "budget": SEPARATION_BUDGET_MIN,
                "reply": _RUN_REPLY,
            },
        ),
        scripted_call(_ADOPT, {"task_id": report.task_id, "reply": _ADOPT_REPLY}),
        scripted_call("verify_strategy", {"reason": "check the adopted strategy"}),
        lead_final(_built_prose(messages), "complete", strategy_changed=True),
    ]


def asks_for_a_separation(lowered: str) -> bool:
    return has_any(lowered, SEPARATION_MARKERS)


class _Step(BaseModel):
    model_config = ConfigDict(
        extra="ignore", populate_by_name=True, from_attributes=True
    )

    id: str
    wdk_step_id: int | None = Field(default=None, alias="wdkStepId")
    primary_input_step_id: str | None = Field(default=None, alias="primaryInputStepId")
    secondary_input_step_id: str | None = Field(
        default=None, alias="secondaryInputStepId"
    )


class _Strategy(BaseModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    steps: list[_Step] | None = None


def _root_wdk_step_id(messages: list[ModelMessage]) -> int | None:
    steps = _Strategy.model_validate(_returned(messages, _READ) or {}).steps or []
    inputs = {s.primary_input_step_id for s in steps} | {
        s.secondary_input_step_id for s in steps
    }
    return next((s.wdk_step_id for s in steps if s.id not in inputs), None)


def adopted_check(messages: list[ModelMessage]) -> ToolCallPart | None:
    """VERIFY's next call on a strategy adopted with its controls, or None."""
    named = dict(_CONTROLS_LINE.findall(head_work_order(messages)))
    if not named:
        return None
    called = acted_tool_names(messages)
    if _READ not in called:
        return scripted_call(_READ, {"summary_only": False})
    if _TEST in called:
        return None
    return scripted_call(
        _TEST,
        {
            "wdk_step_id": _root_wdk_step_id(messages),
            "positive_controls": named["positive"].split(", "),
            "negative_controls": named["negative"].split(", "),
        },
    )
