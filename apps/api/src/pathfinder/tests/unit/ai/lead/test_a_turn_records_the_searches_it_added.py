"""A build and an edit record the searches they added, and the words each keeps."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import CombineOp, flatten_tree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch, sub_agent_dispatch
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.sub_agent_dispatch import build_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    build_step_tree,
    renumber_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_words import AddedSearch
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_GPI_WORDS = "genes with a predicted GPI anchor"
_ORGANISM = {"organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])}


def _exported(criterion_id: str = "c_gpi") -> Criterion:
    return Criterion(
        id=criterion_id,
        text=_GPI_WORDS,
        search_name="GenesByExportPrediction",
        search_display_name="Exported Protein",
        resolved_params=dict(_ORGANISM),
    )


def _taxon() -> Criterion:
    return Criterion(
        id="c_taxon",
        text="P. falciparum 3D7 genes",
        search_name="GenesByTaxon",
        search_display_name="Organism",
        role="seed",
        resolved_params=dict(_ORGANISM),
    )


def _spec(*criteria: Criterion, root: StructureNode) -> OperationalSpec:
    return OperationalSpec(
        goal="GPI anchored proteins",
        criteria=list(criteria),
        structure=SpecStructure(root=root),
    )


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _build_ctx() -> RunContext[LeadDeps]:
    state = pipeline_state(
        user_prompt="Find P. falciparum 3D7 genes with a predicted GPI anchor",
        domain=StrategyDomainState(
            operational_spec=_spec(_exported(), root=_leaf("c_gpi"))
        ),
    )
    return run_context_for(
        lead_deps(state, strategy_session=StrategySession(site_id="plasmodb"))
    )


async def test_a_build_records_the_search_it_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contexts: list[StrategyMutationContext] = []

    async def _fake_build(**kwargs: Any) -> BuildOutcome:
        contexts.append(kwargs["deps"])
        return BuildOutcome(pushed_step_ids=[kwargs["root"].id])

    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _fake_build)
    ctx = _build_ctx()

    delta = await build_strategy(ctx)

    (step_id,) = delta.outcome.pushed_step_ids
    added = AddedSearch(
        step_id=step_id,
        search_display_name="Exported Protein",
        criterion_text=_GPI_WORDS,
    )
    assert delta.added_searches == [added]
    assert ctx.deps.state.turn_markers.added_searches == [added]
    assert dict(contexts[0].criterion_texts) == {step_id: _GPI_WORDS}


def _built() -> tuple[OperationalSpec, StrategySession]:
    spec = _spec(_taxon(), root=_leaf("c_taxon"))
    tree = build_step_tree(spec)
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="GPI", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    session.graph = graph
    return renumber_criteria(spec, tree.step_id_by_criterion), session


async def _edited(
    monkeypatch: pytest.MonkeyPatch,
    built: tuple[OperationalSpec, StrategySession],
    after: OperationalSpec,
) -> tuple[LeadDeps, EditDelta]:
    before, session = built
    state = pipeline_state(
        user_prompt="keep only the GPI anchored ones",
        domain=StrategyDomainState(operational_spec=before.model_copy(deep=True)),
    )
    state.domain.spec_before_turn = before
    deps = lead_deps(state, strategy_session=session)

    async def _fake_frame(**_kwargs: Any) -> FrameResult:
        state.domain.operational_spec = after
        return FrameResult(disposition="spec_ready", summary="reframed")

    async def _fake_commit(**_kwargs: Any) -> CommitResult:
        return CommitResult(description="edited")

    monkeypatch.setattr(edit_dispatch, "run_frame", _fake_frame)
    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _fake_commit)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)
    delta = await run_edit(deps=deps, parent_tool_call_id="t1", reason="GPI")
    assert isinstance(delta, EditDelta)
    return deps, delta


async def test_an_edit_records_the_search_it_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _built()
    before = built[0]
    after = before.model_copy(deep=True)
    after.criteria.append(_exported())
    after.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[_leaf(before.criteria[0].id), _leaf("c_gpi")],
        )
    )

    deps, delta = await _edited(monkeypatch, built, after)

    added = AddedSearch(
        step_id="c_gpi",
        search_display_name="Exported Protein",
        criterion_text=_GPI_WORDS,
    )
    assert delta.added_searches == [added]
    assert deps.state.turn_markers.added_searches == [added]


async def test_an_edit_of_a_value_records_no_added_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built = _built()
    after = built[0].model_copy(deep=True)
    after.criteria[0].resolved_params = {
        "organism": MultiPickValue(values=["Plasmodium vivax P01"])
    }

    deps, delta = await _edited(monkeypatch, built, after)

    assert (delta.added_searches, deps.state.turn_markers.added_searches) == ([], [])
