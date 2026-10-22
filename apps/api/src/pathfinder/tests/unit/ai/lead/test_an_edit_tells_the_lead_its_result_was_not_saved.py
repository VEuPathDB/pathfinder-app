from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import flatten_tree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.spec_tree import build_step_tree, renumber_criteria
from pathfinder.domain.turn_facts import UnsavedSetFact
from pathfinder.platform.config import get_settings
from pathfinder.services.strategies.commit import CommitResult
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

CAP = get_settings().step_genes_cap


def _organism(name: str) -> dict[str, MultiPickValue]:
    return {"organism": MultiPickValue(values=[name])}


def _spec(organism: str) -> OperationalSpec:
    return OperationalSpec(
        goal="every gene of an organism",
        criteria=[
            Criterion(
                id="c_taxon",
                text="the organism's genes",
                search_name="GenesByTaxon",
                search_display_name="Organism",
                role="seed",
                resolved_params=bound(_organism(organism)),
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="c_taxon")
        ),
    )


async def _edit(monkeypatch: pytest.MonkeyPatch, root_count: int) -> EditDelta:
    spec = _spec("Plasmodium falciparum 3D7")
    tree = build_step_tree(spec)
    before = renumber_criteria(spec, tree.step_id_by_criterion)
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Genes", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    session.graph = graph
    root = tree.root.id
    after = before.model_copy(deep=True)
    after.criteria[0].resolved_params = bound(_organism("Plasmodium vivax P01"))
    state = pipeline_state(
        user_prompt="every P. vivax gene instead",
        domain=StrategyDomainState(operational_spec=before.model_copy(deep=True)),
    )
    state.domain.spec_before_turn = before
    deps = lead_deps(state, strategy_session=session)

    async def _frame(**_kwargs: Any) -> FrameResult:
        state.domain.operational_spec = after
        return FrameResult(disposition="spec_ready", summary="reframed")

    async def _commit(**_kwargs: Any) -> CommitResult:
        session.sync_state = WDKSyncState(
            step_counts={root: root_count}, wdk_step_ids={root: 440_299_574}
        )
        return CommitResult(description="edited")

    monkeypatch.setattr(edit_dispatch, "run_frame", _frame)
    monkeypatch.setattr(edit_dispatch, "apply_operations_and_commit", _commit)
    monkeypatch.setattr(edit_dispatch, "get_stream_writer", lambda: lambda _p: None)
    delta = await run_edit(deps=deps, parent_tool_call_id="t1", reason="P. vivax")
    assert isinstance(delta, EditDelta)
    return delta


@pytest.mark.parametrize(
    ("root_count", "told"),
    [
        (12_480, UnsavedSetFact(count=12_480, cap=CAP, record_noun="gene")),
        (5_318, None),
    ],
)
async def test_the_edit_delta_says_whether_the_result_was_saved(
    monkeypatch: pytest.MonkeyPatch, root_count: int, told: UnsavedSetFact | None
) -> None:
    delta = await _edit(monkeypatch, root_count)

    assert (delta.operations_applied, delta.unsaved_gene_set) == (1, told)
