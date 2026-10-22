"""A FRAME question that names a slot the draft does not hold is sent back to
FRAME once, inside its own run, with the slots the draft holds."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext
from veupathdb.domain.parameters import NumberValue

from pathfinder.ai.agents.frame_result_checks import hold_the_questions_to_the_draft
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_CUTOFF = SlotQuestion(
    question="What cutoff should define low variation across isolates?",
    dimension=ConstraintKind.STATISTICAL_THRESHOLD,
    recommended_value="1",
    options=["1", "2"],
    criterion_id="c_low_variation",
    param_name="snp_density_upper",
)


def _expression() -> Criterion:
    return Criterion(
        id="c_blood_expression",
        text="expressed in the blood stage",
        search_name="GenesByRNASeqPercentile",
        resolved_params={
            "min_expression_percentile": BoundValue(
                value=NumberValue(value=80), source="default"
            )
        },
    )


def _variation() -> Criterion:
    return Criterion(
        id="c_low_variation",
        text="do not vary much between isolates",
        search_name="GenesByVariantCharacteristics",
        open_params=[
            OpenSlot(
                param_name="snp_density_upper",
                question="Choose a value for SNV density",
                criterion_id="c_low_variation",
                param_kind="number",
            )
        ],
    )


def _context(*criteria: Criterion) -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    ctx.deps.agent_state.operational_spec_draft = OperationalSpec(
        goal="blood stage genes that do not vary much", criteria=list(criteria)
    )
    return ctx


def _asked(*questions: SlotQuestion) -> FrameResult:
    return FrameResult(disposition="needs_user", open_questions=list(questions))


def test_a_question_on_a_criterion_the_draft_lacks_is_sent_back_twice() -> None:
    ctx = _context(_expression())
    result = _asked(_CUTOFF)

    with pytest.raises(ModelRetry) as sent_back:
        hold_the_questions_to_the_draft(ctx, result)

    told = str(sent_back.value)
    assert "names c_low_variation.snp_density_upper" in told
    assert "The draft holds c_blood_expression: min_expression_percentile" in told
    assert "record the criterion first with set_criterion" in told
    assert "report it in requirement_problems and ask no question about it" in told
    with pytest.raises(ModelRetry):
        hold_the_questions_to_the_draft(ctx, result)
    assert hold_the_questions_to_the_draft(ctx, result) == result.with_gap(
        "questions_bind_nothing",
        "The pass asks questions whose answers bind nothing its draft holds.",
    )


def test_a_question_on_an_open_slot_the_draft_holds_passes() -> None:
    result = _asked(_CUTOFF)

    assert (
        hold_the_questions_to_the_draft(_context(_expression(), _variation()), result)
        is result
    )


def test_a_pass_that_does_not_stop_on_the_user_is_not_read() -> None:
    result = FrameResult(disposition="spec_ready", open_questions=[_CUTOFF])

    assert hold_the_questions_to_the_draft(_context(_expression()), result) is result
