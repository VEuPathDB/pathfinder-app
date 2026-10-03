"""An edit pass that ends in a question pushes nothing: its delta carries no
diff and names the criteria the plan moved as pending."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp, StrategyAst, flatten_tree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch, pre_turn
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import BoundValue
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_SWAP = "Switch the organism on the signal peptide step to P01."


def _leaf(step_id: str, search_name: str) -> dict[str, Any]:
    return {
        "id": step_id,
        "searchName": search_name,
        "parameters": {"organism": {"type": "string", "value": "3D7"}},
    }


def _session() -> StrategySession:
    tree = StrategyAst.model_validate(
        {
            "recordType": "transcript",
            "name": "secreted",
            "root": {
                "id": "root",
                "operator": CombineOp.INTERSECT.value,
                "primaryInput": _leaf("signal", "GenesBySignalPeptide"),
                "secondaryInput": _leaf("tm", "GenesByTransmembraneDomains"),
            },
        }
    )
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="secreted", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts={"root": 288})
    return session


async def _edit_that_stops_on_a_question(monkeypatch: pytest.MonkeyPatch) -> EditDelta:
    state = pipeline_state(user_prompt=_SWAP, domain=StrategyDomainState())
    intent = UserIntent(
        classification=IntentClassification.EDIT_STRATEGY, inferred_goal=_SWAP
    )
    deps: LeadDeps = lead_deps(state, intent=intent, strategy_session=_session())

    async def _frame(**kwargs: Any) -> FrameResult:
        spec = kwargs["deps"].state.domain.operational_spec
        [signal] = [c for c in spec.criteria if c.id == "signal"]
        signal.resolved_params["organism"] = BoundValue(
            value=StringValue(value="P01"), source="chosen"
        )
        return FrameResult(disposition="needs_user", summary="stopped on the TM step")

    async def _no_sheets(**_kwargs: Any) -> dict[str, Any]:
        return {}

    async def _no_marks(*_args: Any) -> dict[str, str]:
        return {}

    monkeypatch.setattr(edit_dispatch, "run_frame", _frame)
    monkeypatch.setattr(pre_turn, "sheet_params_for_searches", _no_sheets)
    monkeypatch.setattr(pre_turn, "organism_parameters", _no_marks)
    result = await run_edit(deps=deps, parent_tool_call_id="t1", reason=_SWAP)
    assert isinstance(result, EditDelta)
    return result


async def test_the_delta_names_the_moved_criterion_as_pending_and_carries_no_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delta = await _edit_that_stops_on_a_question(monkeypatch)

    assert (delta.disposition, delta.diff.changes, delta.pending_step_ids) == (
        "needs_user",
        [],
        ["signal"],
    )
    assert delta.operations_applied == 0
