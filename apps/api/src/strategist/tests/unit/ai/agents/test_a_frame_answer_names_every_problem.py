from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.tools import RunContext

from strategist.ai.agents.frame_answer import hold_the_frame_answer
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.graph.turn_records import TurnMarkers
from strategist.ai.lead.deltas import FrameResult, PassGap
from strategist.domain.refusal import Problem, RefusalKey, RefusalLedger
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from strategist.platform.refusals import SpentRefusal
from strategist.tests.unit.ai.tools.conftest import agent_run_context

_UNKNOWN = RequirementReport(
    requirement="R9", problem=RequirementProblem.SITE_HAS_NO_SEARCH
)
_ROUTED = RequirementReport(
    requirement="R1",
    problem=RequirementProblem.ANOTHER_SITE_ANSWERS,
    site="nowhere",
)
_ANSWER = FrameResult(
    disposition="spec_ready", requirement_problems=[_UNKNOWN, _ROUTED]
)
_GAPS = [
    PassGap(
        kind="report_dropped",
        sentence="The pass reported R9, which the requirement list does not hold.",
    ),
    PassGap(
        kind="structure_names_unbound",
        sentence="The structure names c_tide, which no bound criterion stands for.",
    ),
    PassGap(
        kind="report_dropped",
        sentence=(
            "The pass named 'nowhere' as another site that answers R1, and it is none."
        ),
    ),
]


def _context() -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    state = ctx.deps.agent_state
    state.stated_requirements = [
        Constraint(
            kind=ConstraintKind.UNTYPED,
            label="a reef domain",
            requested_value="a reef domain",
            source=ConstraintSource.USER_EXPLICIT,
        )
    ]
    state.operational_spec_draft = OperationalSpec(
        goal="reef genes",
        criteria=[Criterion(id="c_reef", text="reef", search_name="GenesByReef")],
        structure=SpecStructure(
            root=StructureNode.model_validate(
                {
                    "kind": "combine",
                    "operator": "INTERSECT",
                    "inputs": [
                        {"kind": "leaf", "criterionId": "c_reef"},
                        {"kind": "leaf", "criterionId": "c_tide"},
                    ],
                }
            )
        ),
    )
    return ctx


async def _refused(ctx: RunContext[AgentDeps]) -> str:
    with pytest.raises(ModelRetry) as refused:
        await hold_the_frame_answer(ctx, _ANSWER)
    return refused.value.message


async def test_three_problems_are_refused_together_twice_then_let_through() -> None:
    ctx = _context()

    first = await _refused(ctx)
    second = await _refused(ctx)
    answered = await hold_the_frame_answer(ctx, _ANSWER)

    assert first == second
    assert first.splitlines()[0] == "3 problems:"
    assert [line.split(" ")[1] for line in first.splitlines()[1:]] == [
        "requirement_problems",
        "set_structure",
        "another_site_answers",
    ]
    assert answered == FrameResult(disposition="spec_ready", gaps=_GAPS)


async def test_the_last_answer_is_refused_nothing_and_names_every_gap() -> None:
    ctx = _context()

    answered = await hold_the_frame_answer(replace(ctx, retry=ctx.max_retries), _ANSWER)

    assert answered == FrameResult(disposition="spec_ready", gaps=_GAPS)
    assert ctx.deps.agent_state.answer_ledger == RefusalLedger()


async def test_a_spent_criterion_call_is_named_as_a_gap() -> None:
    ctx = agent_run_context()
    spent = SpentRefusal(
        spent=(
            Problem(
                key=RefusalKey(check="unknown_names", criterion="c_reef"),
                sentence="c_reef names no such parameter.",
            ),
        )
    )
    ctx.deps.refusal_book.spent.append(spent)

    answered = await hold_the_frame_answer(ctx, FrameResult(disposition="spec_ready"))

    assert answered == FrameResult(
        disposition="spec_ready",
        gaps=[PassGap(kind="refusal_spent", sentence=spent.note)],
    )


def test_a_record_of_the_old_counters_loads_with_an_empty_ledger() -> None:
    markers = TurnMarkers.model_validate(
        {
            "outputRefusals": 2,
            "refusedRules": ["unverified_build"],
            "refusedDigests": ["x"],
        }
    )

    assert markers.answer_ledger == RefusalLedger()
