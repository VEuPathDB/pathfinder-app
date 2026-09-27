"""A spec derived from, or replayed onto, a live strategy carries the organism
parameter each search marks."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead import answered_strategy, pre_turn
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.database import no_database

_RNASEQ = "GenesByRNASeqpfal3D7_Su_seven_stages_rnaSeq_RSRC"
_FALCIPARUM = "Plasmodium falciparum 3D7"
_TAXON = StrategyStepNode(
    id="step_taxon",
    search_name="GenesByTaxon",
    parameters={"organism": MultiPickValue(values=[_FALCIPARUM])},
)


def _session(seed: StrategyStepNode | None = None) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Falciparum stages", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_join",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=seed or _TAXON,
            secondary_input=StrategyStepNode(
                id="step_stages",
                search_name=_RNASEQ,
                parameters={
                    "profileset_generic": StringValue(value="Pfal3D7 Su seven stages")
                },
            ),
        )
    )
    graph.recompute_roots()
    session.graph = graph
    return session


@pytest.fixture
def sheet(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _sheets(**_kwargs: Any) -> dict[str, frozenset[str]]:
        return {
            "GenesByTaxon": frozenset({"organism"}),
            "GenesByText": frozenset({"text_expression", "text_search_organism"}),
            _RNASEQ: frozenset({"profileset_generic"}),
        }

    monkeypatch.setattr(pre_turn, "sheet_params_for_searches", _sheets)
    monkeypatch.setattr(answered_strategy, "sheet_params_for_searches", _sheets)


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="keep only the falciparum genes",
        domain=StrategyDomainState(),
    )


def _context(session: StrategySession) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=session,
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )


@pytest.mark.usefixtures("sheet")
async def test_a_hydrated_criterion_carries_the_organism_its_search_marks() -> None:
    refreshed = await refresh_live_strategy_state(_state(), _context(_session()))

    spec = refreshed.domain.operational_spec
    assert spec is not None
    assert {c.id: c.organism_param for c in spec.criteria} == {
        "step_taxon": "organism",
        "step_stages": None,
    }


@pytest.mark.usefixtures("sheet")
async def test_a_search_swapped_outside_takes_the_mark_of_its_new_search() -> None:
    """The mark belongs to the search, so a rebound criterion reads it again."""
    state = _state()
    hydrated = await refresh_live_strategy_state(state, _context(_session()))
    text_seed = StrategyStepNode(
        id="step_taxon",
        search_name="GenesByText",
        parameters={
            "text_expression": StringValue(value="kinase"),
            "text_search_organism": MultiPickValue(values=[_FALCIPARUM]),
        },
    )

    refreshed = await refresh_live_strategy_state(
        hydrated, _context(_session(text_seed))
    )

    for spec in (refreshed.domain.operational_spec, refreshed.domain.answered_spec):
        assert spec is not None
        assert {c.id: (c.search_name, c.organism_param) for c in spec.criteria} == {
            "step_taxon": ("GenesByText", "text_search_organism"),
            "step_stages": (_RNASEQ, None),
        }
