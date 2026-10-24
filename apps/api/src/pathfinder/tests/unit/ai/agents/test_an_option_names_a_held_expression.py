from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext
from veupathdb_mcp.catalog import PhyleticPattern

from pathfinder.ai.agents.frame_option_checks import hold_an_option_to_a_held_expression
from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.expression_handles import (
    BuiltPattern,
    expression_handle,
)
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.domain.strategy.readings import Reading
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_EXPRESSION = "phyletic_expression"
_BUILT = "pfal=0 AND tgon>=1 OR pfal=1 AND tgon>=2"
_UNKNOWN = "expr:000000000000"
_ADAPTER: TypeAdapter[PhyleticPattern] = TypeAdapter(PhyleticPattern)
_PATTERN = _ADAPTER.validate_python(
    {"kind": "count", "of": {"kind": "codes", "codes": ["APIC"]}, "condition": "absent"}
)


def _context(refusals: int = 0) -> RunContext[AgentDeps]:
    ctx = agent_run_context(site_id="orthomcl")
    state = ctx.deps.agent_state
    state.built_expressions[expression_handle(_BUILT)] = BuiltPattern(
        expression=_BUILT, pattern=_PATTERN, reading="absent from APIC"
    )
    state.refusals = refusals
    return ctx


def _asked(*values: str) -> FrameResult:
    return FrameResult(
        disposition="needs_user",
        open_questions=[
            SlotQuestion(
                question="Which comparison do you mean?",
                dimension=ConstraintKind.OTHER,
                recommended_value="More proteins in tgon",
                criterion_id="c_more",
                param_name=_EXPRESSION,
                readings=[
                    Reading(label=f"Reading {i}", value=value)
                    for i, value in enumerate(values)
                ],
            )
        ],
    )


def test_an_option_naming_an_unknown_handle_is_sent_back() -> None:
    ctx = _context()

    with pytest.raises(ModelRetry) as sent_back:
        hold_an_option_to_a_held_expression(
            ctx, _asked(expression_handle(_BUILT), _UNKNOWN)
        )

    assert str(sent_back.value) == (
        f"c_more.{_EXPRESSION} offers {[_UNKNOWN]}, and no expression of this "
        "conversation is held under that handle, so the card would bind nothing. "
        "Offer a handle build_phyletic_expression returned, or build the reading "
        "first."
    )
    assert ctx.deps.agent_state.refusals == 1


def test_options_naming_held_handles_and_typed_expressions_pass() -> None:
    asked = _asked(expression_handle(_BUILT), "APIC>=1T AND MAMM=0T")

    assert hold_an_option_to_a_held_expression(_context(), asked) == asked


def test_at_the_bound_the_question_is_dropped_with_a_named_gap() -> None:
    held = hold_an_option_to_a_held_expression(
        _context(refusals=REFUSALS_PER_CHECK),
        _asked(expression_handle(_BUILT), _UNKNOWN),
    )

    assert isinstance(held, FrameResult)
    assert (held.open_questions, held.gaps) == (
        [],
        [
            PassGap(
                kind="expression_handle_unknown",
                sentence=(
                    f"The pass offered {[_UNKNOWN]} on c_more.{_EXPRESSION}, which "
                    "no held expression answers, so the question was dropped."
                ),
            )
        ],
    )
