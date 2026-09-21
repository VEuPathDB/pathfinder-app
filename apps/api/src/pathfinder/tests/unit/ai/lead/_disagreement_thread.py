"""One thread driven through the pre-turn refresh and the edit dispatch.

Only the FRAME pass, the sheet read and the commit are stand-ins: the refresh,
the dispatch checks, the diff and the planner are the production ones.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal

import pytest
from assistant_core.graph.turn_state import PendingApproval
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch, frame_dispatch, pre_turn
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.ai.lead.sub_agent_stream import SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_diff import CriterionChange
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

SURFACE = "step_0a1b2c3d"
STAGE = "step_1b2c3d4e"
ROOT = "step_2c3d4e5f"
STAGE_PERCENTILE = "min_expression_percentile"
STAGE_TIMEPOINT = "timepoint"

Draft = Callable[[OperationalSpec], OperationalSpec]
FrameDisposition = Literal["spec_ready", "needs_user", "needs_research"]


def leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def joined(operator: CombineOp, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=list(inputs))


def surface_step() -> StrategyStepNode:
    return StrategyStepNode(
        id=SURFACE, search_name="GenesBySignalPeptide", display_name="surface"
    )


def stage_step() -> StrategyStepNode:
    return StrategyStepNode(
        id=STAGE,
        search_name="GenesByRNASeqEvidence",
        display_name="merozoite stage",
        parameters={
            STAGE_PERCENTILE: NumberValue(value=80),
            STAGE_TIMEPOINT: NumberValue(value=40),
        },
    )


def built_tree() -> StrategyStepNode:
    return StrategyStepNode(
        id=ROOT,
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=surface_step(),
        secondary_input=stage_step(),
    )


def built_spec() -> OperationalSpec:
    """The spec the build left: each criterion addressed by its step."""
    stage = stage_step()
    return OperationalSpec(
        goal="vaccine candidates",
        criteria=[
            Criterion(
                id=SURFACE,
                text="predicted surface proteins",
                search_name="GenesBySignalPeptide",
                role="seed",
            ),
            Criterion(
                id=STAGE,
                text="expressed in merozoites",
                search_name=stage.search_name,
                resolved_params=dict(stage.parameters),
            ),
        ],
        structure=SpecStructure(
            root=joined(CombineOp.INTERSECT, leaf(SURFACE), leaf(STAGE))
        ),
    )


def session_holding(*roots: StrategyStepNode) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="candidates", site_id="plasmodb")
    graph.record_type = "transcript"
    for root in roots:
        graph.steps.update(flatten_tree(root))
    graph.recompute_roots()
    session.graph = graph
    return session


def recorded(*step_ids: str) -> BuildOutcome:
    return BuildOutcome(
        node_results=[
            NodeResult(node_id=step_id, search_name="recorded", status="ok")
            for step_id in step_ids
        ]
    )


def kept(*criterion_ids: str) -> list[CriterionChange]:
    return [
        CriterionChange(criterion_id=cid, disposition="kept") for cid in criterion_ids
    ]


class DisagreementThread:
    """A thread whose committed spec and strategy are set apart by the test."""

    def __init__(
        self,
        monkeypatch: pytest.MonkeyPatch,
        *,
        spec: OperationalSpec,
        session: StrategySession,
        recorded_build: BuildOutcome | None = None,
    ) -> None:
        self.monkeypatch = monkeypatch
        self.session = session
        self.committed: list[GraphOperation] = []
        self.deps: LeadDeps = lead_deps(
            pipeline_state(
                user_prompt="change the strategy",
                domain=StrategyDomainState(
                    operational_spec=spec, last_build_outcome=recorded_build
                ),
            ),
            strategy_session=session,
        )

        async def _commit(**kwargs: Any) -> CommitResult:
            graph = self.graph
            for op in kwargs["ops"]:
                apply_operation(graph, op)
            self.committed.extend(kwargs["ops"])
            return CommitResult(description="edited")

        async def _sheets(**kwargs: Any) -> dict[str, frozenset[str]]:
            return {name: frozenset() for name in kwargs["search_names"]}

        monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _commit)
        monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)
        monkeypatch.setattr(pre_turn, "sheet_params_for_searches", _sheets)

    @property
    def graph(self) -> StrategyGraph:
        graph = self.session.get_graph(None)
        assert graph is not None
        return graph

    @property
    def spec(self) -> OperationalSpec:
        spec = self.deps.state.domain.operational_spec
        assert spec is not None
        return spec

    @property
    def criteria(self) -> list[str]:
        return [c.id for c in self.spec.criteria]

    async def next_turn(self, *, resumes_parked_call: bool = False) -> None:
        """Run the refresh every turn starts with, over the state as it stands."""
        state = self.deps.state
        state.pending_approval = (
            PendingApproval(phase="frame", tool_call_id="t1", tool_name="consult_user")
            if resumes_parked_call
            else None
        )
        refreshed = await refresh_live_strategy_state(state, self.deps.runtime)
        refreshed.pending_approval = None
        self.deps = lead_deps(refreshed, strategy_session=self.session)

    def frames(
        self,
        draft: Draft,
        *,
        declared: list[CriterionChange],
        disposition: FrameDisposition = "spec_ready",
    ) -> None:
        """Make the next FRAME pass turn the workspace it finds into ``draft``."""

        async def _pass(**kwargs: Any) -> FrameResult:
            agent_deps: AgentDeps = kwargs["agent_deps"]
            found = agent_deps.agent_state.operational_spec_draft
            assert found is not None
            agent_deps.agent_state.operational_spec_draft = draft(
                found.model_copy(deep=True)
            )
            return FrameResult(
                disposition=disposition, summary="framed", changes=declared
            )

        self.monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _pass)

    async def edit(self, *, resume: SubAgentResume | None = None) -> EditDelta | str:
        """The delta the dispatch returns, or the words of its refusal."""
        try:
            delta = await run_edit(
                deps=self.deps,
                parent_tool_call_id="t1",
                reason="change the strategy",
                resume=resume,
            )
        except ModelRetry as refusal:
            return refusal.message
        assert isinstance(delta, EditDelta)
        return delta
