"""An edit classified as a narrowing that would answer another organism's
genes is refused before anything is committed."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import flatten_tree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations import GraphOperation
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_tree import build_step_tree, renumber_criteria
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.domain.strategy._orthology import (
    TARGET,
    leg,
    seed_criteria,
    seed_node,
)

_ASKED = "Keep only those with syntenic orthologs in Plasmodium vivax P01."


def _held() -> tuple[OperationalSpec, StrategySession]:
    spec = OperationalSpec(
        goal="signal peptide and 2 to 99 transmembrane domains",
        criteria=seed_criteria(),
        structure=SpecStructure(root=seed_node()),
    )
    tree = build_step_tree(spec)
    graph = StrategyGraph(graph_id="g1", name="surface", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    session = StrategySession(site_id="plasmodb")
    session.graph = graph
    return renumber_criteria(spec, tree.step_id_by_criterion), session


def _one_way(held: OperationalSpec) -> OperationalSpec:
    signal, tm = (c.id for c in held.criteria)
    return held.model_copy(
        update={
            "criteria": [*held.criteria, leg("c_syntenic_vivax_p01", TARGET, "yes")],
            "structure": SpecStructure(
                root=StructureNode(
                    kind="transform",
                    criterion_id="c_syntenic_vivax_p01",
                    inputs=[seed_node(signal, tm)],
                )
            ),
        }
    )


async def test_a_tighten_edit_that_moves_the_organism_commits_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held, session = _held()
    state = pipeline_state(
        user_prompt=_ASKED,
        domain=StrategyDomainState(operational_spec=held.model_copy(deep=True)),
    )
    state.domain.spec_before_turn = held
    deps = lead_deps(state, strategy_session=session)
    deps.intent = UserIntent(
        classification=IntentClassification.EDIT_STRATEGY,
        inferred_goal="Restrict the current results to genes with syntenic orthologs",
        edit_direction="tighten",
    )
    committed: list[GraphOperation] = []

    async def _frame(**_kwargs: Any) -> FrameResult:
        state.domain.operational_spec = _one_way(held)
        return FrameResult(disposition="spec_ready", summary="one-way transform")

    async def _commit(**kwargs: Any) -> CommitResult:
        committed.extend(kwargs["ops"])
        return CommitResult(description="edited")

    monkeypatch.setattr(edit_dispatch, "run_frame", _frame)
    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _commit)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)

    with pytest.raises(ModelRetry) as refused:
        await run_edit(deps=deps, parent_tool_call_id="t1", reason=_ASKED)

    assert f"would answer genes of {TARGET}" in str(refused.value)
    assert committed == []
    restored = deps.state.domain.operational_spec
    assert restored is not None
    assert [c.id for c in restored.criteria] == [c.id for c in held.criteria]
