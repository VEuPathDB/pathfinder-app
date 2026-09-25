"""An edit reads a live strategy no spec describes, and a refusal names offered tools."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import ModelRetry

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import edit_dispatch, pre_turn
from pathfinder.ai.lead.deltas import EditDelta, FrameResult
from pathfinder.ai.lead.edit_dispatch import run_edit
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.intent_gate import tools_the_turn_offers
from pathfinder.tests.unit.ai.lead._answered_draft import classify, draft_deps, framed
from pathfinder.tests.unit.ai.lead.conftest import session_with_one_step

_MESSAGE = "export the up genes and add genes with a signal peptide"
_EDIT_TOOLS = ["frame_problem", "build_strategy", "edit_strategy"]


@pytest.fixture
def work_orders(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """FRAME records its order and asks the user, so nothing is pushed."""
    orders: list[str] = []

    async def _sheets(**_kwargs: Any) -> dict[str, frozenset[str]]:
        return {}

    async def _asks(**kwargs: Any) -> FrameResult:
        orders.append(kwargs["work_order"])
        return FrameResult(disposition="needs_user", summary="which evidence?")

    monkeypatch.setattr(pre_turn, "sheet_params_for_searches", _sheets)
    monkeypatch.setattr(edit_dispatch, "run_frame", _asks)
    return orders


async def test_an_edit_over_a_step_no_spec_states_edits_that_step(
    work_orders: list[str],
) -> None:
    deps = draft_deps(
        _MESSAGE,
        domain=StrategyDomainState(),
        strategy_session=session_with_one_step(step_id="eda_step"),
    )
    classify(deps, IntentClassification.NEW_STRATEGY)
    assert tools_the_turn_offers(deps, _EDIT_TOOLS) == frozenset({"edit_strategy"})

    delta = await run_edit(deps=deps, parent_tool_call_id="e1", reason="add it")

    assert isinstance(delta, EditDelta)
    assert delta.disposition == "needs_user"
    found = deps.state.domain.spec_before_dispatch
    assert found is not None
    assert [(c.id, c.search_name) for c in found.criteria] == [
        ("eda_step", "GenesByText")
    ]
    assert "The strategy holds 1 criteria now:" in work_orders[0]
    assert "- [eda_step] " in work_orders[0]


async def test_an_edit_after_this_turns_frame_names_only_the_build(
    work_orders: list[str],
) -> None:
    deps = draft_deps(_MESSAGE, domain=StrategyDomainState())
    classify(deps, IntentClassification.NEW_STRATEGY)
    deps.state.domain.operational_spec = framed("signal peptide")
    deps.state.turn_markers.framed = True
    offered = tools_the_turn_offers(deps, _EDIT_TOOLS)

    with pytest.raises(ModelRetry) as refused:
        await run_edit(deps=deps, parent_tool_call_id="e1", reason="add it")

    assert offered == frozenset({"build_strategy", "edit_strategy"})
    assert refused.value.message == (
        "edit_strategy needs a strategy to edit, and this conversation has none. Call "
        "build_strategy to build the spec this turn framed."
    )
    assert work_orders == []
