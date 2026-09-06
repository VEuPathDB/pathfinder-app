"""Verification picks its checks from what the turn changed, and says so.

Adding one transform to a strategy that already exists is answered by a count
check. Enrichment is a minutes-long background job, so it is not offered on
that turn unless the user asked for it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from veupathdb.domain.strategy.build_outcome import BuildOutcome
from veupathdb.domain.strategy.graph_model import StepKind, StrategyStep
from veupathdb.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from veupathdb.domain.strategy.session import StrategyGraph, StrategySession

from pathfinder.ai.lead import sub_agent_tools
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification, verify_strategy
from pathfinder.ai.tools.toolsets import verification
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.sub_agents import (
    agent_tool_names,
    pinned_sub_agent,
    toolset_tool_names,
)
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    called_tool_names,
    final_result_part,
    lead_deps,
    pipeline_state,
)

_ENRICHMENT = "run_gene_set_enrichment"
_ROOT_COUNT = 16
_DESCRIPTION = verify_strategy.__doc__ or ""
_USER_FACING = ["enrich", "control", "sample"]

pytestmark = pytest.mark.usefixtures("collector")


class TestTheDispatchToolNamesWhatItCanDo:
    @pytest.mark.parametrize("capability", _USER_FACING)
    def test_a_capability_is_named(self, capability: str) -> None:
        assert _DESCRIPTION.lower().count(capability) >= 1

    def test_it_still_says_it_verifies(self) -> None:
        assert "verif" in _DESCRIPTION.lower()


class TestTheCapabilitiesAreReallyThere:
    def test_enrichment_belongs_to_the_verification_toolset(self) -> None:
        assert "run_gene_set_enrichment" in toolset_tool_names(
            verification.build_toolset()
        )

    def test_the_lead_does_not_carry_enrichment_itself(self) -> None:
        # If it ever does, the dispatch note above is the thing to correct.
        assert "run_gene_set_enrichment" not in agent_tool_names(build_lead_agent())


def _criterion(index: int, search_name: str) -> Criterion:
    return Criterion(
        id=f"c{index}",
        text=f"criterion {index}",
        search_name=search_name,
        confidence=0.9,
    )


def _three_criteria() -> list[Criterion]:
    return [
        _criterion(1, "GenesByText"),
        _criterion(2, "GenesByTaxon"),
        _criterion(3, "GenesByMolecularWeight"),
    ]


def _spec(criteria: list[Criterion]) -> OperationalSpec:
    return OperationalSpec(
        goal="Transform the result into P. vivax P01 orthologs.",
        criteria=criteria,
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=criteria[0].id),
        ),
    )


def _session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("graph-1", "Orthologs", "plasmodb")
    graph.record_type = "transcript"
    for index in range(1, 5):
        add_step_to_graph(
            graph,
            StrategyStep(
                id=f"s{index}",
                kind=StepKind.SEARCH,
                search_name="GenesByText",
            ),
        )
    session.add_graph(graph)
    session.sync_state = WDKSyncState(
        wdk_step_ids={f"s{i}": 440186100 + i for i in range(1, 5)},
        step_counts={f"s{i}": _ROOT_COUNT for i in range(1, 5)},
        wdk_strategy_id=330423363,
    )
    return session


def _deps() -> LeadDeps:
    state = pipeline_state(
        user_prompt=(
            "Now add a step at the end that transforms the result into "
            "P. vivax P01 orthologs."
        ),
    )
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1", "s2", "s3", "s4"],
        wdk_strategy_id=330423363,
        root_count=_ROOT_COUNT,
    )
    return lead_deps(state, strategy_session=_session())


def _one_step_edit() -> LeadDeps:
    """One transform added to a strategy of three steps."""
    deps = _deps()
    before = _three_criteria()
    deps.state.domain.spec_before_turn = _spec(before)
    deps.state.domain.operational_spec = _spec(
        [*before, _criterion(4, "GenesByOrthologs")],
    )
    return deps


def _fresh_build() -> LeadDeps:
    """A turn that built the whole strategy from nothing."""
    deps = _deps()
    deps.state.domain.operational_spec = _spec(_three_criteria())
    return deps


class _Script:
    """Record the tools the run offers, then check the counts and answer."""

    def __init__(self) -> None:
        self.offered: set[str] = set()

    def part(self, messages: list[ModelMessage], info: AgentInfo) -> ToolCallPart:
        self.offered = {tool.name for tool in info.function_tools}
        if "get_strategy" not in called_tool_names(messages):
            return ToolCallPart(
                tool_name="get_strategy",
                args={"summary_only": False},
                tool_call_id="call_get_strategy",
            )
        return final_result_part(
            {
                "digest": {
                    "disposition": "done",
                    "prose": f"The strategy returns {_ROOT_COUNT} records.",
                    "reason": "Counts read from the strategy.",
                    "success": True,
                },
            },
        )

    def model(self) -> FunctionModel:
        def _fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
            return ModelResponse(parts=[self.part(messages, info)])

        async def _stream(
            messages: list[ModelMessage],
            info: AgentInfo,
        ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
            part = self.part(messages, info)
            yield {
                0: DeltaToolCall(
                    name=part.tool_name,
                    json_args=part.args_as_json_str(),
                    tool_call_id=part.tool_call_id,
                ),
            }

        return FunctionModel(_fn, stream_function=_stream, model_name="scripted")


async def _verify(
    monkeypatch: pytest.MonkeyPatch,
    deps: LeadDeps,
    script: _Script,
    *,
    enrichment_requested: bool = False,
) -> VerificationDelta:
    monkeypatch.setattr(sub_agent_tools, "get_mock_model", script.model)
    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions="Follow the script.",
    ):
        result = await run_verification(
            deps=deps,
            parent_tool_call_id="lead_call_verify",
            reason="confirm the transform",
            enrichment_requested=enrichment_requested,
        )
    assert isinstance(result, VerificationDelta)
    return result


async def test_a_one_step_edit_is_not_offered_enrichment(
    monkeypatch: pytest.MonkeyPatch,
    collector: ChunkCollector,
) -> None:
    script = _Script()

    delta = await _verify(monkeypatch, _one_step_edit(), script)

    assert _ENRICHMENT not in script.offered
    assert collector.step_tool_names() == {"get_strategy"}
    assert delta.digest.prose == "The strategy returns 16 records."


async def test_the_user_can_still_ask_for_enrichment_on_an_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _Script()

    await _verify(monkeypatch, _one_step_edit(), script, enrichment_requested=True)

    assert "run_gene_set_enrichment" in script.offered


async def test_a_fresh_build_is_still_offered_enrichment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = _Script()

    await _verify(monkeypatch, _fresh_build(), script)

    assert "run_gene_set_enrichment" in script.offered
