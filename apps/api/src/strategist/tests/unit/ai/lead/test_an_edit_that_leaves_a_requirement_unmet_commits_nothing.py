"""An edit whose spec leaves a stated requirement met by no step commits nothing."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.strategy import flatten_tree

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead import edit_dispatch
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.edit_dispatch import run_edit
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrthologValue,
)
from strategist.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.operations import GraphOperation
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.domain.strategy.spec_tree import build_step_tree
from strategist.platform.refusals import ProblemsRefusal
from strategist.services.strategies.commit import CommitResult
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from strategist.tests.unit.domain.strategy._orthology import (
    TARGET,
    leg,
    seed_criteria,
    seed_node,
)

_ASKED = "Carry these to their syntenic orthologs in Plasmodium vivax P01."
_SYNTENIC = Constraint(
    kind=ConstraintKind.ORTHOLOG,
    requested_value=f"syntenic orthologs in {TARGET}",
    label=f"syntenic orthologs in {TARGET}",
    source=ConstraintSource.USER_EXPLICIT,
    quote=f"syntenic orthologs in {TARGET}",
    value=OrthologValue(organisms=[TARGET], syntenic=True),
)


def _held() -> tuple[OperationalSpec, StrategySession]:
    spec = OperationalSpec(
        goal="signal peptide and 2 to 99 transmembrane domains",
        criteria=seed_criteria(),
        structure=SpecStructure(root=seed_node()),
    )
    tree = build_step_tree(spec)
    graph = StrategyGraph(graph_id="g1", name="surface", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree)
    graph.recompute_roots()
    session = StrategySession(site_id="plasmodb")
    session.graph = graph
    return spec, session


def _carried_unlinked(held: OperationalSpec) -> OperationalSpec:
    signal, tm = (c.id for c in held.criteria)
    return held.model_copy(
        update={
            "criteria": [*held.criteria, leg("c_all_vivax_p01", TARGET, "no")],
            "structure": SpecStructure(
                root=StructureNode(
                    kind="transform",
                    criterion_id="c_all_vivax_p01",
                    inputs=[seed_node(signal, tm)],
                )
            ),
        }
    )


async def test_an_edit_no_step_of_which_meets_the_syntenic_requirement_commits_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held, session = _held()
    state = pipeline_state(
        user_prompt=_ASKED,
        domain=StrategyDomainState(
            operational_spec=held.model_copy(deep=True), requirements=[_SYNTENIC]
        ),
    )
    state.domain.spec_before_turn = held
    deps = lead_deps(state, strategy_session=session)
    committed: list[GraphOperation] = []

    async def _frame(**_kwargs: Any) -> FrameResult:
        state.domain.operational_spec = _carried_unlinked(held)
        return FrameResult(disposition="spec_ready", notes="all orthologs")

    async def _commit(**kwargs: Any) -> CommitResult:
        committed.extend(kwargs["ops"])
        return CommitResult(description="edited")

    monkeypatch.setattr(edit_dispatch, "run_frame", _frame)
    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _commit)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)

    with pytest.raises(ProblemsRefusal) as refused:
        await run_edit(deps=deps, parent_tool_call_id="t1", reason=_ASKED)

    assert (
        f"The requirement 'syntenic orthologs in {TARGET}' is not met by any step"
        in str(refused.value)
    )
    assert committed == []
