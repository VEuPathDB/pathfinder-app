"""A placeholder the site left in a step of a strategy the turn reads back is
shown as not set, as it is when the turn binds it."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKSearch

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.ai.lead.turn_facts import _parameters
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import sheet_params
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.recorded_searches import client_search

_LOCATION = "GenesByLocation"
_PROMPT = "(Example: Pf3D7_04_v3)"


@pytest.fixture(autouse=True)
def _recorded_sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _record_type(*_args: Any, **_kwargs: Any) -> str:
        return "transcript"

    async def _definition(*_args: Any, **_kwargs: Any) -> WDKSearch:
        return client_search("search_genes_by_location")

    monkeypatch.setattr(sheet_params, "resolve_search_record_type", _record_type)
    monkeypatch.setattr(sheet_params, "read_search_definition", _definition)


def _session(sequence: str) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Chromosome 6", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_loc",
            search_name=_LOCATION,
            parameters={
                "organismSinglePick": MultiPickValue(
                    values=["Plasmodium falciparum 3D7"]
                ),
                "chromosomeOptional": SinglePickValue(value="Pf3D7_06_v3"),
                "sequenceId": StringValue(value=sequence),
                "start_point": StringValue(value="1"),
                "end_point": StringValue(value="0"),
            },
        )
    )
    graph.recompute_roots()
    session.graph = graph
    return session


async def _sequence_row(sequence: str) -> list[str]:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="how many genes does it hold?",
        domain=StrategyDomainState(),
    )
    context = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=_session(sequence),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )
    refreshed = await refresh_live_strategy_state(state, context)
    spec = refreshed.domain.operational_spec
    assert spec is not None
    [criterion] = spec.criteria
    return [
        line
        for fact in _parameters(criterion, "gene", [])
        if fact.name == "sequenceId"
        for line in fact.lines()
    ]


async def test_a_placeholder_in_a_strategy_read_back_is_not_set() -> None:
    assert await _sequence_row(_PROMPT) == [
        "Genomic sequence ID: not set (site placeholder)"
    ]


async def test_a_sequence_in_a_strategy_read_back_is_its_value() -> None:
    assert await _sequence_row("Pf3D7_04_v3") == ["Genomic sequence ID: Pf3D7_04_v3"]
