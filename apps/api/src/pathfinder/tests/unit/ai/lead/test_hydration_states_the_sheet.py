"""The spec a turn derives from a live strategy states only the sheet's parameters.

A hidden WDK parameter reaches the stored step, and the edit tools refuse it,
so a criterion that stated it would cost a refused call on every edit.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead import pre_turn
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.database import no_database

_SEARCH = "GenesByRNASeqpfal3D7_Su_seven_stages_rnaSeq_RSRC"
_DATASET_URL = "https://PlasmoDB.org/a/app/record/dataset/DS_66f9e70b8a"


def _session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Gametocyte kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_7c2e770b",
            search_name=_SEARCH,
            parameters={
                "profileset_generic": StringValue(value="Pfal3D7 Su seven stages"),
                "dataset_url": StringValue(value=_DATASET_URL),
            },
        )
    )
    graph.recompute_roots()
    session.graph = graph
    return session


def _context(session: StrategySession) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=session,
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="use the gametocyte time course instead",
        domain=StrategyDomainState(),
    )


@pytest.fixture
def sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _sheets(**_kwargs: Any) -> dict[str, frozenset[str]]:
        return {_SEARCH: frozenset({"profileset_generic"})}

    monkeypatch.setattr(pre_turn, "sheet_params_for_searches", _sheets)


@pytest.mark.usefixtures("sheet")
async def test_a_hidden_parameter_is_not_stated_by_the_derived_criterion() -> None:
    refreshed = await refresh_live_strategy_state(_state(), _context(_session()))

    spec = refreshed.domain.operational_spec
    assert spec is not None
    criterion = spec.criteria[0]
    assert "dataset_url" not in criterion.resolved_params
    assert criterion.resolved_params["profileset_generic"] == StringValue(
        value="Pfal3D7 Su seven stages"
    )
