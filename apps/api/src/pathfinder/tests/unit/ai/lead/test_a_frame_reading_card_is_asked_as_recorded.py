from __future__ import annotations

from collections.abc import Collection, Mapping
from uuid import uuid4

import pytest
from assistant_core.conversation.vercel_adapter import DeferredToolHint
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from pydantic import BaseModel
from pydantic_ai.ui.vercel_ai.response_types import (
    ToolInputAvailableChunk,
    ToolInputStartChunk,
)
from veupathdb.domain.parameters import ParamValue
from veupathdb_mcp.catalog import ParameterInfo, ValidatedParams

from pathfinder.ai.graph._lead_card_hold import CardHold
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import lead_consult
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.lead_consult import (
    consult_user,
    refuse_a_card_that_binds_nothing,
)
from pathfinder.ai.lead.recorded_cards import completed_hint, the_card_asked
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import Constraint
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.services.strategies import reading_check
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_CRITERION = "c_copy_number_comparison"
_EXPRESSION = "phyletic_expression"
_RECORDED_FRAME = {
    "disposition": "needs_user",
    "summary": "The required expression is still open.",
    "openQuestions": [
        {
            "question": (
                "What minimum Toxoplasma-over-Plasmodium copy-number expansion "
                "should count? The search compares average copy numbers across the "
                "two genome lists using ratio bands; choose the smallest ratio you "
                "want to include."
            ),
            "dimension": "fold_change",
            "recommendedValue": "Any higher copy number (greater than 1x)",
            "readings": [
                {"label": "Any higher (greater than 1x)", "value": "r=1"},
                {"label": "At least 1.5-fold higher", "value": "r=1.5"},
                {"label": "At least 2-fold higher", "value": "r=2"},
            ],
            "requirements": ["R4"],
            "criterionId": _CRITERION,
            "paramName": _EXPRESSION,
        }
    ],
}
_RECORDED_LEAD_CARD = {
    "id": "comparison_basis",
    "prompt": (
        "What should count as evidence that an orthogroup is expanded in "
        "Toxoplasma relative to Plasmodium? Please describe the comparison basis "
        "in your own words - for example, copy number per genome or presence "
        "across taxa."
    ),
    "kind": "free_text",
    "dimension": "other",
    "allowNotes": True,
}


_STATED = [
    Constraint.model_validate(c | {"source": "user_explicit"})
    for c in (
        {
            "kind": "organism",
            "requestedValue": "Toxoplasma",
            "label": "Toxoplasma genomes",
        },
        {
            "kind": "organism",
            "requestedValue": "Plasmodium",
            "label": "Plasmodium genomes",
        },
        {
            "kind": "record_type",
            "requestedValue": "orthogroups",
            "label": "orthogroups",
        },
        {
            "kind": "other",
            "requestedValue": "more genes per genome in Toxoplasma than Plasmodium",
            "label": "expanded gene families",
        },
    )
]
_EXPANDED = _STATED[3].key


def _thread_holding_the_frame_question() -> LeadDeps:
    spec = OperationalSpec(
        criteria=[
            Criterion(
                id=_CRITERION,
                text="higher copy number per genome in one genus",
                search_name="GroupsByPhyleticPattern",
                record_class="group",
                open_params=[OpenSlot(criterion_id=_CRITERION, param_name=_EXPRESSION)],
            )
        ]
    )
    domain = StrategyDomainState(operational_spec=spec, requirements=list(_STATED))
    domain.record_questions(
        FrameResult.model_validate(_RECORDED_FRAME).questions(spec, _STATED)
    )
    return lead_deps(
        pipeline_state(
            "orthomcl",
            user_prompt="the researcher's message",
            user_message_id=uuid4(),
            domain=domain,
        )
    )


_READINGS = [
    "Any higher (greater than 1x)",
    "At least 1.5-fold higher",
    "At least 2-fold higher",
]


def test_the_card_shows_the_frame_readings_beside_a_free_text_question() -> None:
    deps = _thread_holding_the_frame_question()
    written = [CardQuestion.model_validate(_RECORDED_LEAD_CARD)]

    readings, own = the_card_asked(written, deps.state.domain.open_questions)

    assert [o.label for o in readings.options] == _READINGS
    assert (own.prompt, own.options) == (written[0].prompt, [])
    refuse_a_card_that_binds_nothing(
        run_context_for(deps, "call_card"), written, reply="Which basis?"
    )


def test_the_held_card_reaches_the_wire_with_the_frame_readings() -> None:
    deps = _thread_holding_the_frame_question()
    hold = CardHold()
    written = {"questions": [_RECORDED_LEAD_CARD], "reply": "Which basis?"}
    for chunk in (
        ToolInputStartChunk(tool_call_id="call_card", tool_name="consult_user"),
        ToolInputAvailableChunk(
            tool_call_id="call_card", tool_name="consult_user", input=written
        ),
    ):
        hold.admit(chunk)

    released = hold.release(TurnFacts(), deps.state.domain.open_questions)

    [shown] = [c for c in released if isinstance(c, ToolInputAvailableChunk)]
    card = _Card.model_validate(shown.input)
    assert [[o.label for o in q.options] for q in card.questions] == [_READINGS, []]
    assert card.reply == "Which basis?"


class _Card(BaseModel):
    questions: list[CardQuestion]
    reply: str


@pytest.fixture
def no_site(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _sheets(
        *, site_id: str, search_names: Collection[str]
    ) -> dict[str, list[ParameterInfo]]:
        del site_id, search_names
        return {}

    async def _validate(
        _search: object, *, parameters: Mapping[str, ParamValue], callbacks: object
    ) -> ValidatedParams:
        del callbacks
        return ValidatedParams(params=dict(parameters))

    monkeypatch.setattr(lead_consult, "sheet_params_for_searches", _sheets)
    monkeypatch.setattr(reading_check, "validate_parameters", _validate)


async def test_an_answer_to_the_completed_card_closes_the_frame_question(
    no_site: None,
) -> None:
    deps = _thread_holding_the_frame_question()
    [recorded] = deps.state.domain.open_questions
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id="q1",
                prompt=recorded.question,
                chosen_labels=["At least 2-fold higher"],
            )
        ]
    }

    await consult_user(
        run_context_for(deps, "call_card"),
        [CardQuestion.model_validate(_RECORDED_LEAD_CARD)],
        reply="Which basis?",
    )

    assert [q.question for q in deps.state.domain.answered_questions] == [
        recorded.question,
        _RECORDED_LEAD_CARD["prompt"],
    ]


def test_a_lead_question_on_the_same_requirement_gives_way_to_the_recorded_one() -> (
    None
):
    deps = _thread_holding_the_frame_question()
    reworded = CardQuestion.model_validate(
        _RECORDED_LEAD_CARD | {"requirement": _EXPANDED}
    )

    [shown] = the_card_asked([reworded], deps.state.domain.open_questions)

    assert ([o.label for o in shown.options], shown.requirement) == (
        _READINGS,
        _EXPANDED,
    )


async def test_the_answered_record_holds_the_questions_the_card_showed(
    no_site: None,
) -> None:
    deps = _thread_holding_the_frame_question()
    [recorded] = deps.state.domain.open_questions
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id="q1",
                prompt=recorded.question,
                chosen_labels=["At least 2-fold higher"],
            )
        ]
    }

    await consult_user(
        run_context_for(deps, "call_card"),
        [CardQuestion.model_validate(_RECORDED_LEAD_CARD | {"requirement": _EXPANDED})],
        reply="Which basis?",
    )

    assert [q.question for q in deps.state.domain.answered_questions] == [
        recorded.question
    ]


def test_a_resumed_card_is_announced_as_the_card_showed_it() -> None:
    deps = _thread_holding_the_frame_question()
    hint = DeferredToolHint(
        tool_call_id="call_card",
        tool_name="consult_user",
        tool_args={"questions": [_RECORDED_LEAD_CARD], "reply": "Which basis?"},
    )

    announced = completed_hint(hint, deps.state.domain.open_questions)

    card = _Card.model_validate(announced.tool_args)
    assert [[o.label for o in q.options] for q in card.questions] == [_READINGS, []]
