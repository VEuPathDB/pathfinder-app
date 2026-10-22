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
from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.requirement_reports import RecordRole, RecordTypeRole
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_PROTEINS = Constraint(
    kind=ConstraintKind.RECORD_TYPE,
    label="record type",
    requested_value="protein",
    source=ConstraintSource.USER_EXPLICIT,
)
_GROUPS = Constraint(
    kind=ConstraintKind.RECORD_TYPE,
    label="record type",
    requested_value="ortholog groups",
)
_ORGANISM = Constraint(
    kind=ConstraintKind.ORGANISM,
    label="organism",
    requested_value="Plasmodium falciparum 3D7",
    source=ConstraintSource.USER_EXPLICIT,
)


def _result(*roles: tuple[str, str]) -> dict[str, object]:
    return {
        "summary": "Bound the groups of the 3D7 kinases.",
        "disposition": "needs_research",
        "recordTypes": [
            {"requirement": number, "role": role} for number, role in roles
        ],
    }


async def _run(
    answers: list[dict[str, object]],
    held: dict[str, RecordRole] | None = None,
) -> tuple[FrameResult, list[str], list[str]]:
    told: list[str] = []
    shown: list[str] = []

    def _frame(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        shown.append(last.instructions or "")
        told.extend(
            str(p.content) for p in last.parts if isinstance(p, RetryPromptPart)
        )
        answer = answers.pop(0) if len(answers) > 1 else answers[0]
        return ModelResponse(parts=[ToolCallPart("final_result", answer)])

    deps = agent_run_context(site_id="orthomcl").deps
    deps.agent_state.stated_requirements = [_ORGANISM, _PROTEINS, _GROUPS]
    deps.agent_state.held_record_roles = {} if held is None else held
    agent = build_frame_agent()

    with agent.override(model=FunctionModel(_frame, model_name="scripted")):
        run = await agent.run("FRAME work order: frame it", deps=deps)

    assert isinstance(run.output, FrameResult)
    return run.output, told, shown


async def test_frame_reads_each_requirement_with_its_kind() -> None:
    _, _, shown = await _run([_result(("R2", "through"), ("R3", "answer"))])

    assert (
        "## Requirements the researcher stated\n"
        "- R1 (organism): Plasmodium falciparum 3D7\n"
        "- R2 (record_type): protein\n"
        "- R3 (record_type, assumed): ortholog groups"
    ) in shown[0]


async def test_a_record_type_left_without_a_role_is_sent_back_once() -> None:
    output, told, _ = await _run(
        [_result(("R2", "through")), _result(("R2", "through"), ("R3", "answer"))]
    )

    assert told == [
        (
            "record_types states no role for R3. Give each record-type requirement "
            "in 'Requirements the researcher stated' a role: answer when the result "
            "is those records, through when the tree passes through them."
        )
    ]
    assert output.record_types == [
        RecordTypeRole(requirement="R2", role="through"),
        RecordTypeRole(requirement="R3", role="answer"),
    ]
    assert output.gaps == []


async def test_a_role_an_earlier_pass_stated_needs_no_restating() -> None:
    output, told, _ = await _run(
        [_result(("R3", "answer"))], held={_PROTEINS.key: "through"}
    )

    assert (told, output.gaps) == ([], [])


async def test_a_role_still_missing_at_the_bound_is_judged_as_the_answer() -> None:
    output, told, _ = await _run([_result(("R2", "through"))])

    assert len(told) == REFUSALS_PER_CHECK
    assert output.record_types == [RecordTypeRole(requirement="R2", role="through")]
    assert output.gaps == [
        PassGap(
            kind="record_role_missing",
            sentence=(
                "The pass stated no role for the record type 'ortholog groups', "
                "so it is judged as the class the result must be."
            ),
        )
    ]
