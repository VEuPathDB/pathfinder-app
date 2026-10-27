from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest
from assistant_core.graph.turn_state import UserQuestionAnswer
from pydantic import BaseModel
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb_mcp.catalog import PhyleticPattern, ValidatedParams

from pathfinder.ai.agents.frame_reading_checks import hold_the_readings_to_the_site
from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.readings import refused_picks
from pathfinder.domain.strategy.expression_handles import (
    BuiltPattern,
    UnknownExpressionError,
)
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.readings import Reading
from pathfinder.services.strategies import reading_check
from pathfinder.services.strategies.reading_check import site_spelling
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_RECORDED = (
    Path(__file__).parents[3] / "fixtures/turns/orthomcl_one_build_ready_passes.json"
)
_EXPRESSION = "phyletic_expression"
_ANY_GENOME, _HALF, _EACH_SPECIES = (
    "expr:e0361c9efeb0",
    "expr:09d29cd47d43",
    "expr:91380a965b00",
)
_HANDLES = (_ANY_GENOME, _HALF, _EACH_SPECIES)


class _Build(BaseModel):
    pattern: PhyleticPattern


class _Pass(BaseModel):
    build: _Build


class _Recorded(BaseModel):
    passes: dict[str, _Pass]


def _pattern() -> PhyleticPattern:
    recorded = _Recorded.model_validate_json(_RECORDED.read_text())
    return recorded.passes["a_conversation_1"].build.pattern


def _written(handle: str) -> str:
    return f"pfal>=1T AND tgon=0T {handle[-4:]}"


def _criterion() -> Criterion:
    return Criterion(
        id="c_shared_plasmodium_not_toxo",
        text="Ortholog groups present in all Plasmodium species",
        search_name="GroupsByPhyleticPattern",
        record_class="group",
        resolved_params={
            _EXPRESSION: BoundValue(
                value=StringValue(value=_written(_EACH_SPECIES)), source="chosen"
            )
        },
    )


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    found: list[str] = []

    async def _validate(
        _search: object, *, parameters: Mapping[str, ParamValue], callbacks: object
    ) -> ValidatedParams:
        del callbacks
        found.extend(value.to_wire() for value in parameters.values())
        return ValidatedParams(params=dict(parameters))

    monkeypatch.setattr(reading_check, "validate_parameters", _validate)
    return found


def _built() -> dict[str, BuiltPattern]:
    return {
        handle: BuiltPattern(
            expression=_written(handle), pattern=_pattern(), reading=handle
        )
        for handle in _HANDLES
    }


async def test_each_recorded_handle_reaches_the_site_as_its_expression(
    sent: list[str],
) -> None:
    state = AgentToolState(
        operational_spec_draft=OperationalSpec(criteria=[_criterion()]),
        built_expressions=_built(),
    )
    question = SlotQuestion(
        question="Present in which Plasmodium genomes?",
        recommended_value="each species",
        criterion_id="c_shared_plasmodium_not_toxo",
        param_name=_EXPRESSION,
        readings=[Reading(label=h, value=h) for h in _HANDLES],
    )

    held = await hold_the_readings_to_the_site(
        agent_run_context(agent_state=state),
        FrameResult(disposition="needs_user", open_questions=[question]),
    )

    assert [w for w in sent if w.startswith("expr:")] == []
    assert sorted(set(sent)) == sorted(_written(h) for h in _HANDLES)
    assert held == FrameResult(disposition="needs_user", open_questions=[question])


async def test_a_handle_no_build_holds_is_refused_before_the_site(
    sent: list[str],
) -> None:
    with pytest.raises(UnknownExpressionError):
        await site_spelling(
            "orthomcl", "group", _criterion(), _EXPRESSION, _ANY_GENOME, {}
        )

    assert sent == []


async def test_a_question_offering_an_unheld_handle_is_sent_back(
    sent: list[str],
) -> None:
    state = AgentToolState(
        operational_spec_draft=OperationalSpec(criteria=[_criterion()]),
    )
    question = SlotQuestion(
        question="Present in which Plasmodium genomes?",
        recommended_value="each species",
        criterion_id="c_shared_plasmodium_not_toxo",
        param_name=_EXPRESSION,
        readings=[Reading(label=h, value=h) for h in _HANDLES],
    )

    with pytest.raises(ModelRetry) as refused:
        await hold_the_readings_to_the_site(
            agent_run_context(agent_state=state),
            FrameResult(disposition="needs_user", open_questions=[question]),
        )

    assert _ANY_GENOME in str(refused.value)
    assert sent == []


async def test_a_criterion_bound_to_a_handle_sends_nothing_for_another_value(
    sent: list[str],
) -> None:
    criterion = _criterion().model_copy(
        update={
            "resolved_params": {
                _EXPRESSION: BoundValue(
                    value=StringValue(value=_EACH_SPECIES), source="chosen"
                )
            }
        }
    )

    with pytest.raises(UnknownExpressionError):
        await site_spelling(
            "orthomcl", "group", criterion, "organism", "pfal", _expressions()
        )

    assert sent == []


def _expressions() -> dict[str, str]:
    return {handle: _written(handle) for handle in _HANDLES}


async def test_a_picked_reading_naming_a_handle_is_checked_as_its_expression(
    sent: list[str],
) -> None:
    question = SlotQuestion(
        question="Present in which Plasmodium genomes?",
        recommended_value="each species",
        criterion_id="c_shared_plasmodium_not_toxo",
        param_name=_EXPRESSION,
        readings=[Reading(label=h, value=h) for h in _HANDLES],
    ).typed(_criterion(), noun="group")
    state = pipeline_state(
        "orthomcl",
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(criteria=[_criterion()]),
            open_questions=[question],
            built_expressions=_built(),
        ),
    )
    picked = [o.label for o in question.options if o.offered_reading() is not None]

    refused = await refused_picks(
        state,
        [
            UserQuestionAnswer(
                question_id="q1", prompt=question.question, chosen_labels=picked
            )
        ],
    )

    assert (refused, [w for w in sent if w.startswith("expr:")]) == ({}, [])
    assert set(sent) >= {_written(h) for h in _HANDLES}
