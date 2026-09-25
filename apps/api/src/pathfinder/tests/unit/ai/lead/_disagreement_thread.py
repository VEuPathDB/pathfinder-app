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
    subtree_ids,
)

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import (
    answered_strategy,
    edit_dispatch,
    frame_dispatch,
    pre_turn,
    sub_agent_dispatch,
)
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.lead_tools import clear_strategy, delete_step
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.ai.lead.sub_agent_dispatch import build_strategy
from pathfinder.ai.lead.sub_agent_stream import SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import conversation, strategy_edits
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.constraints import OpenQuestion
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_diff import (
    CriterionChange,
    CriterionDisposition,
    SpecDiff,
)
from pathfinder.domain.strategy.spec_reconciliation import spec_the_strategy_holds
from pathfinder.domain.strategy.stated_shape import criteria_with_steps, stated_shape
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests._support.analysis_catalog import serve_the_catalog
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._disagreement_facts import StepFacts, graph_facts
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


def declared(
    disposition: CriterionDisposition, *criterion_ids: str
) -> list[CriterionChange]:
    """What a FRAME pass says it did to the criteria it started with."""
    return [
        CriterionChange(criterion_id=cid, disposition=disposition)
        for cid in criterion_ids
    ]


def kept(*criterion_ids: str) -> list[CriterionChange]:
    return declared("kept", *criterion_ids)


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
        self.written_while_framing = False
        """Whether a canvas commit landed between a dispatch's start and its push."""
        self.workspaces: list[OperationalSpec] = []
        """The workspace each FRAME pass found, newest last."""
        self.work_orders: list[str] = []
        """The work order each FRAME pass received, newest last."""
        graph = session.get_graph(None)
        answered = (
            None
            if graph is None or not graph.steps
            else spec_the_strategy_holds(spec.model_copy(deep=True), graph.steps)
        )
        self.deps: LeadDeps = lead_deps(
            pipeline_state(
                user_prompt="change the strategy",
                domain=StrategyDomainState(
                    operational_spec=spec,
                    last_build_outcome=recorded_build,
                    # The thread last answered with this spec over the strategy
                    # as it stands; a test writes the graph after that to say
                    # what was written outside it.
                    answered_spec=answered,
                    answered_graph=(
                        graph.to_strategy_ast() if graph is not None else None
                    ),
                ),
            ),
            strategy_session=session,
        )

        async def _commit(**kwargs: Any) -> CommitResult:
            graph = self.graph
            dropped: list[str] = []
            for op in kwargs["ops"]:
                dropped.extend(apply_operation(graph, op).dropped_step_ids)
            self.committed.extend(kwargs["ops"])
            return CommitResult(
                description="edited", dropped_step_ids=sorted(set(dropped))
            )

        async def _commit_one(**kwargs: Any) -> CommitResult:
            return await _commit(ops=[kwargs["op"]])

        async def _sheets(**kwargs: Any) -> dict[str, frozenset[str]]:
            """The sheet of a search, taken from the steps that run it."""
            return {
                name: frozenset(
                    param
                    for step in self.graph.steps.values()
                    if step.search_name == name
                    for param in step.parameters
                )
                for name in kwargs["search_names"]
            }

        async def _persisted(**_kwargs: object) -> None:
            return None

        serve_the_catalog(monkeypatch)
        monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _commit)
        monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)
        monkeypatch.setattr(pre_turn, "sheet_params_for_searches", _sheets)
        monkeypatch.setattr(answered_strategy, "sheet_params_for_searches", _sheets)
        monkeypatch.setattr(strategy_edits, "apply_and_commit", _commit_one)
        monkeypatch.setattr(
            conversation, "persist_strategy_ast_to_conversation", _persisted
        )

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

    @property
    def before_turn(self) -> OperationalSpec:
        spec = self.deps.state.domain.spec_before_turn
        assert spec is not None
        return spec

    @property
    def before_dispatch(self) -> OperationalSpec:
        spec = self.deps.state.domain.spec_before_dispatch
        assert spec is not None
        return spec

    def facts(self) -> dict[str, StepFacts]:
        """Every live step, in the form two turns are compared by."""
        return graph_facts(self.graph)

    @property
    def answered(self) -> OperationalSpec:
        spec = self.deps.state.domain.answered_spec
        assert spec is not None
        return spec

    def assert_invariants(self) -> None:
        """What the plan and the strategy owe each other after every step.

        The answered spec states the strategy the graph holds, the answered
        tree is that graph, and a plan with nothing pending is the answer.
        """
        domain = self.deps.state.domain
        answered = domain.answered_spec
        if answered is None:
            return
        if not self.written_while_framing:
            # A commit that lands mid-pass is not one this thread has answered
            # to; the next turn plays it onto the spec.
            assert domain.answered_graph == self.graph.to_strategy_ast()
        held = set(self.graph.steps)
        assert structure_criteria(answered.structure) <= held
        root = self.graph.primary_root_id()
        if root is not None:
            reached = set(subtree_ids(root, self.graph.steps))
            shape = stated_shape(
                graph=self.graph,
                root_id=root,
                criteria=criteria_with_steps(
                    [c.id for c in answered.criteria], self.graph.steps
                ),
                outside=held - reached,
            )
            assert (shape.unstated, shape.lost, shape.stranded) == ((), (), ())
        plan = domain.operational_spec
        if plan is not None and not self._pending(plan, answered, held):
            assert plan == answered

    @staticmethod
    def _pending(
        plan: OperationalSpec, answered: OperationalSpec, held: set[str]
    ) -> bool:
        """What the plan states and the strategy has not taken.

        A criterion with no live step is one the strategy has not built; one
        the answer holds and the plan does not is a drop it has not pushed;
        one the plan holds and the answer does not is an option it has not
        absorbed.
        """
        unbuilt = structure_criteria(plan.structure) - held
        moved = {c.id for c in plan.criteria} ^ {c.id for c in answered.criteria}
        return bool(unbuilt or moved)

    def ledger_diff(self) -> SpecDiff:
        """What the Lead's ledger says this turn did to the spec it entered on."""
        diff = derive_ledger(self.deps.state, None).frame.spec_diff()
        assert diff is not None
        return diff

    async def delete(self, step_id: str) -> None:
        """Run the Lead's delete over the live strategy, as a turn does."""
        await delete_step(
            run_context_for(self.deps, "t_delete"),
            step_id=step_id,
            reply="I will make this change and report what it takes with it.",
        )
        self.assert_invariants()

    async def clear(self) -> None:
        await clear_strategy(
            run_context_for(self.deps, "t_clear"),
            confirm=True,
            reply="I will make this change and report what it takes with it.",
        )
        self.assert_invariants()

    async def build(self) -> BuildOutcome:
        """Build the committed spec, with the WDK push standing in."""

        async def _build(**kwargs: Any) -> BuildOutcome:
            root: StrategyStepNode = kwargs["root"]
            graph = self.graph
            graph.steps = flatten_tree(root)
            graph.recompute_roots()
            graph.last_step_id = root.id
            return BuildOutcome(pushed_step_ids=list(graph.steps))

        self.monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _build)
        self.monkeypatch.setattr(
            sub_agent_dispatch, "get_stream_writer", lambda: lambda _p: None
        )
        delta = await build_strategy(run_context_for(self.deps))
        self.assert_invariants()
        return delta.outcome

    async def frame(self) -> FrameResult | str:
        """The result of one FRAME dispatch, or the words of its refusal."""
        try:
            result = await run_frame(
                deps=self.deps,
                parent_tool_call_id="t1",
                work_order=frame_work_order("frame it", self.deps),
            )
        except ModelRetry as refusal:
            self.assert_invariants()
            return refusal.message
        assert isinstance(result, FrameResult)
        self.assert_invariants()
        return result

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
        self.assert_invariants()

    def frames(
        self,
        draft: Draft,
        *,
        declared: list[CriterionChange],
        disposition: FrameDisposition = "spec_ready",
        asks: list[OpenQuestion] | None = None,
        while_framing: Callable[[StrategyGraph], None] | None = None,
    ) -> None:
        """Make the next FRAME pass turn the workspace it finds into ``draft``.

        ``asks`` are the questions the pass ends on, and ``while_framing``
        writes the graph while the pass runs, which is a canvas commit landing
        between the dispatch's start and its push.
        """

        self.written_while_framing = False

        async def _pass(**kwargs: Any) -> FrameResult:
            agent_deps: AgentDeps = kwargs["agent_deps"]
            found = agent_deps.agent_state.operational_spec_draft
            assert found is not None
            self.workspaces.append(found.model_copy(deep=True))
            self.work_orders.append(kwargs["run"].work_order)
            if while_framing is not None:
                while_framing(self.graph)
                self.written_while_framing = True
            agent_deps.agent_state.operational_spec_draft = draft(
                found.model_copy(deep=True)
            )
            return FrameResult(
                disposition=disposition,
                summary="framed",
                changes=declared,
                open_questions=list(asks or []),
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
            self.assert_invariants()
            return refusal.message
        assert isinstance(delta, EditDelta)
        self.assert_invariants()
        return delta
