"""Two dispatches over one criterion: one frames it open, the next builds it.

The first edit leaves a criterion the user still has to answer, so the thread's
spec states a criterion the strategy holds no step for. The second edit fills
the value and pushes the step.
"""

from __future__ import annotations

from typing import Any, Literal

import pytest
from veupathdb.domain.parameters import MultiPickValue, NumberValue
from veupathdb.domain.strategy import CombineOp, flatten_tree

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch, frame_dispatch
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    build_step_tree,
    renumber_criteria,
)
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_diff import CriterionChange
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_OPEN = "c_mass_spec"
_PARAM = "min_peptide_count"
_SEARCH = "GenesByMassSpec"

FrameDisposition = Literal["spec_ready", "needs_user", "needs_research"]


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _built() -> tuple[OperationalSpec, StrategySession]:
    """The strategy on screen: two steps under one combine."""
    spec = OperationalSpec(
        goal="vaccine candidates",
        criteria=[
            Criterion(
                id="c_surface",
                text="predicted surface proteins",
                search_name="GenesBySignalPeptide",
                role="seed",
            ),
            Criterion(
                id="c_stage",
                text="expressed in merozoites",
                search_name="GenesByRNASeqEvidence",
                resolved_params={"organism": MultiPickValue(values=["Pf3D7"])},
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[_leaf("c_surface"), _leaf("c_stage")],
            )
        ),
    )
    tree = build_step_tree(spec)
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="candidates", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    session.graph = graph
    return renumber_criteria(spec, tree.step_id_by_criterion), session


def _mass_spec(value: float | None = None) -> Criterion:
    return Criterion(
        id=_OPEN,
        text="detected in the merozoite proteome",
        search_name=_SEARCH,
        resolved_params={} if value is None else {_PARAM: NumberValue(value=value)},
        open_params=[]
        if value is not None
        else [OpenSlot(criterion_id=_OPEN, param_name=_PARAM)],
    )


def _with_the_open_criterion(
    before: OperationalSpec, value: float | None
) -> OperationalSpec:
    """The draft FRAME leaves: the built criteria, plus the one under decision."""
    draft = before.model_copy(deep=True)
    draft.criteria = [c for c in draft.criteria if c.id != _OPEN]
    draft.criteria.append(_mass_spec(value))
    assert before.structure is not None
    root = before.structure.root
    if _OPEN not in {node.criterion_id for node in root.inputs}:
        draft.structure = SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[root.model_copy(deep=True), _leaf(_OPEN)],
            )
        )
    return draft


class _Thread:
    """One thread, driven one dispatch at a time."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        before, session = _built()
        self.committed: list[GraphOperation] = []
        self.deps: LeadDeps = lead_deps(
            pipeline_state(
                user_prompt="add direct proteome evidence",
                domain=StrategyDomainState(
                    operational_spec=before.model_copy(deep=True)
                ),
            ),
            strategy_session=session,
        )
        self.built_ids = [c.id for c in before.criteria]
        self.monkeypatch = monkeypatch

        async def _commit(**kwargs: Any) -> CommitResult:
            self.committed.extend(kwargs["ops"])
            return CommitResult(description="edited")

        monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _commit)
        monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)

    def frames(
        self,
        *,
        value: float | None,
        disposition: FrameDisposition,
        declared: list[CriterionChange],
    ) -> None:
        """Make the next FRAME pass leave this draft behind."""

        async def _pass(**kwargs: Any) -> FrameResult:
            agent_deps: AgentDeps = kwargs["agent_deps"]
            found = self.deps.state.domain.spec_before_dispatch
            assert found is not None
            agent_deps.agent_state.operational_spec_draft = _with_the_open_criterion(
                found, value
            )
            return FrameResult(
                disposition=disposition, summary="framed", changes=declared
            )

        self.monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _pass)

    async def edit(self) -> EditDelta:
        delta = await run_edit(
            deps=self.deps, parent_tool_call_id="t1", reason="add the filter"
        )
        assert isinstance(delta, EditDelta)
        return delta

    @property
    def criteria(self) -> list[str]:
        spec = self.deps.state.domain.operational_spec
        return [c.id for c in spec.criteria] if spec is not None else []


def _kept(*criterion_ids: str) -> list[CriterionChange]:
    return [
        CriterionChange(criterion_id=cid, disposition="kept") for cid in criterion_ids
    ]


async def test_the_open_criterion_is_committed_and_pushes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _Thread(monkeypatch)
    thread.frames(value=None, disposition="needs_user", declared=[])

    delta = await thread.edit()

    assert delta.disposition == "needs_user"
    assert thread.criteria == [*thread.built_ids, _OPEN]
    assert thread.committed == []


async def test_the_next_edit_pushes_the_step_the_answer_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _Thread(monkeypatch)
    thread.frames(value=None, disposition="needs_user", declared=[])
    await thread.edit()
    thread.frames(
        value=2,
        disposition="spec_ready",
        declared=_kept(*thread.built_ids, _OPEN),
    )

    delta = await thread.edit()

    assert [op.kind for op in thread.committed] == ["addLeaf", "addCombine"]
    assert sorted(delta.preserved_step_ids) == sorted(thread.built_ids)


async def test_a_criterion_with_no_step_is_never_reported_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The edit builds it, so no earlier turn reported an id for it."""
    thread = _Thread(monkeypatch)
    thread.frames(value=None, disposition="needs_user", declared=[])
    await thread.edit()
    thread.frames(
        value=None,
        disposition="spec_ready",
        declared=_kept(*thread.built_ids, _OPEN),
    )

    delta = await thread.edit()

    assert _OPEN not in delta.preserved_step_ids
    assert [op.kind for op in thread.committed] == ["addLeaf", "addCombine"]
