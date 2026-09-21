"""``set_criterion`` keeps a new criterion out of the step address space.

``step_<8 hex>`` is the id the step minter produces, and the reconciliation
reads an id of that shape as a step the strategy lost. A new criterion named
that way leaves the spec before it can be built.
"""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry, RunContext
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree, generate_step_id

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone.frame_spec import SetCriterionResult, set_criterion
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    KINASE_PARAMS,
    Proposals,
    genes_by_text,
    serve_search,
)

_SEARCH = "GenesByText"
_LIVE = "step_3fa0e628"


def _session(*step_ids: str) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
    graph.record_type = "transcript"
    for step_id in step_ids:
        graph.steps.update(
            flatten_tree(StrategyStepNode(id=step_id, search_name=_SEARCH))
        )
    graph.recompute_roots()
    session.add_graph(graph)
    return session


def _ctx(state: AgentToolState, *step_ids: str) -> RunContext[AgentDeps]:
    return agent_run_context(agent_state=state, strategy_session=_session(*step_ids))


async def _bind(
    state: AgentToolState,
    criterion_id: str,
    *step_ids: str,
    params: Proposals | None = None,
) -> SetCriterionResult:
    return returned(
        await set_criterion(
            _ctx(state, *step_ids),
            criterion_id=criterion_id,
            text="kinases",
            search_name=_SEARCH,
            params=params if params is not None else KINASE_PARAMS,
        ),
        SetCriterionResult,
    )


async def test_a_new_criterion_of_the_minted_shape_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    state = AgentToolState()

    with pytest.raises(ModelRetry) as excinfo:
        await _bind(state, generate_step_id())

    assert "step_" in str(excinfo.value)
    assert state.operational_spec_draft.criteria == []


async def test_the_sheet_request_is_refused_before_it_opens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first call of the pair carries the id, so it is refused there."""
    serve_search(monkeypatch, genes_by_text)
    state = AgentToolState()

    with pytest.raises(ModelRetry):
        await _bind(state, generate_step_id(), params=None)

    assert state.open_sheets == {}


async def test_the_id_of_a_step_the_strategy_holds_binds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A built criterion is addressed by its own step, so that id is its name."""
    serve_search(monkeypatch, genes_by_text)
    state = AgentToolState()

    result = await _bind(state, _LIVE, _LIVE)

    assert result.criterion_id == _LIVE
    assert [c.id for c in state.operational_spec_draft.criteria] == [_LIVE]


async def test_an_id_outside_the_step_shape_binds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, genes_by_text)
    state = AgentToolState()

    result = await _bind(state, "c_kinases")

    assert result.criterion_id == "c_kinases"
    assert [c.id for c in state.operational_spec_draft.criteria] == ["c_kinases"]
