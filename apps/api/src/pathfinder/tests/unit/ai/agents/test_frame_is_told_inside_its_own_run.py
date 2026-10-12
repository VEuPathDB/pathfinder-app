"""FRAME's result checks run inside FRAME's run: the pass reads the correction
and answers again, and the caller receives only the answer it gave last."""

from __future__ import annotations

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel

from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_GPI = Constraint(
    kind=ConstraintKind.OTHER,
    label="predicted GPI anchor",
    requested_value="predicted GPI anchor",
    source=ConstraintSource.USER_EXPLICIT,
)


def _reports(number: str) -> dict[str, object]:
    return {
        "summary": "No search on this site states a predicted GPI anchor.",
        "disposition": "needs_research",
        "requirementProblems": [
            {"requirement": number, "problem": "site_has_no_search"}
        ],
    }


async def test_a_number_the_list_lacks_is_corrected_before_the_caller_reads_it() -> (
    None
):
    told: list[str] = []

    def _frame(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        retries = [p for p in last.parts if isinstance(p, RetryPromptPart)]
        told.extend(str(p.content) for p in retries)
        number = "R1" if retries else "R4"
        return ModelResponse(parts=[ToolCallPart("final_result", _reports(number))])

    deps = agent_run_context().deps
    deps.agent_state.stated_requirements = [_GPI]
    agent = build_frame_agent()

    with agent.override(model=FunctionModel(_frame, model_name="scripted")):
        run = await agent.run("FRAME work order: frame it", deps=deps)

    assert isinstance(run.output, FrameResult)
    assert run.output.requirement_problems == [
        RequirementReport(
            requirement="R1", problem=RequirementProblem.SITE_HAS_NO_SEARCH
        )
    ]
    [sent_back] = told
    assert sent_back == (
        "requirement_problems names ['R4'], and the list holds R1. A report names "
        "a requirement by its number in 'Requirements the researcher stated'. Use "
        "one of those numbers, or leave the entry out and say it in summary."
    )
