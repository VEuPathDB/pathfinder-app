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
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.constraints import Constraint
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.tests._support.organism_specs import (
    ME49,
    PF3D7,
    chain,
    groups,
    id_list,
    proteins,
    signal_peptide,
    single,
    taxon,
)
from pathfinder.tests._support.orthomcl_counts import CLADE_ONLY, replayed_counts
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_READY = {"summary": "Bound the ME49 proteins.", "disposition": "spec_ready"}
_REMEDY = (
    "R1 asks for Toxoplasma gondii ME49 (organism), and no step of the draft "
    "limits its records to an organism. A unit of a phyletic expression or the "
    "text of a transform does not. Add a step that does, such as the sequence "
    "search by taxonomy (ByTaxonomy) intersected with the proteins, or a search "
    "whose organism parameter names it. If no search can, report R1 in "
    "requirement_problems."
)


async def _run(
    draft: OperationalSpec, requirements: list[Constraint], site_id: str = "orthomcl"
) -> tuple[FrameResult, list[str], int]:
    told: list[str] = []

    def _frame(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del info
        last = messages[-1]
        assert isinstance(last, ModelRequest)
        told.extend(
            str(p.content) for p in last.parts if isinstance(p, RetryPromptPart)
        )
        return ModelResponse(parts=[ToolCallPart("final_result", _READY)])

    deps = agent_run_context(site_id=site_id).deps
    deps.agent_state.stated_requirements = requirements
    deps.agent_state.operational_spec_draft = draft
    agent = build_frame_agent()

    with (
        replayed_counts(CLADE_ONLY),
        agent.override(model=FunctionModel(_frame, model_name="scripted")),
    ):
        run = await agent.run("FRAME work order: frame it", deps=deps)

    assert isinstance(run.output, FrameResult)
    return run.output, told, deps.agent_state.refusals


async def test_an_organism_met_only_by_a_phyletic_unit_is_sent_back() -> None:
    output, told, _ = await _run(chain(groups(), proteins()), [ME49])

    assert told == [_REMEDY, _REMEDY]
    assert output.gaps == [
        PassGap(
            kind="organism_step_missing",
            sentence=(
                "No step limits the records to the organism R1 asks for: "
                "Toxoplasma gondii ME49."
            ),
        )
    ]


async def test_an_organism_met_by_a_taxonomy_step_passes() -> None:
    output, told, _ = await _run(chain(groups(), proteins(), taxon()), [ME49])

    assert (told, output.gaps) == ([], [])


async def test_a_request_with_no_organism_requirement_is_untouched() -> None:
    output, told, _ = await _run(chain(groups(), proteins()), [])

    assert (told, output.gaps) == ([], [])


async def test_an_id_list_the_researcher_gave_meets_the_organism() -> None:
    output, told, refusals = await _run(single(id_list()), [PF3D7], site_id="plasmodb")

    assert (told, output.gaps, refusals) == ([], [], 0)


async def test_another_site_is_sent_to_an_organism_parameter() -> None:
    _, told, _ = await _run(single(signal_peptide()), [PF3D7], site_id="plasmodb")

    assert told[0] == (
        "R1 asks for Plasmodium falciparum 3D7 (organism), and no step of the draft "
        "limits its records to an organism. A unit of a phyletic expression or the "
        "text of a transform does not. Bind the organism parameter of a search "
        "that has one to it. If no search can, report R1 in requirement_problems."
    )
