"""The turn opens reading what each step of the live strategy and of the tree
the thread last answered runs on, so a strategy no check has read grounds a
data-type requirement by its dataset's assay."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead import answered_strategy, pre_turn
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.pre_turn import refresh_live_strategy_state
from pathfinder.domain.strategy.constraints import ConstraintKind, ConstraintStatus
from pathfinder.domain.strategy.data_marks import DataMarks
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.sheets import visible_sheet
from pathfinder.tests.unit.ai.lead.conftest import requirement

_PERCENTILE = "GenesByRNASeqpfal3D7_Gomez-Diaz_asexual_stages_ebi_rnaSeq_RSRCPercentile"
_SIMILAR = "GenesByProfileSimilarity"


def _session(search_name: str) -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Expressed", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_expr",
            search_name=search_name,
            parameters={"min_percentile": NumberValue(value=90)},
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
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="which genes are expressed",
        domain=StrategyDomainState(),
    )
    state.domain.requirements = [
        requirement(ConstraintKind.DATA_TYPE, "RNA-Seq dataset", "RNA-Seq")
    ]
    return state


@pytest.fixture(autouse=True)
def _sheets(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _read(**_kwargs: Any) -> dict[str, list[ParameterInfo]]:
        return {
            name: visible_sheet(["min_percentile"]) for name in (_PERCENTILE, _SIMILAR)
        }

    monkeypatch.setattr(pre_turn, "sheet_params_for_searches", _read)
    monkeypatch.setattr(answered_strategy, "sheet_params_for_searches", _read)


async def test_a_hydrated_strategy_grounds_by_its_datasets_assay() -> None:
    refreshed = await refresh_live_strategy_state(
        _state(), _context(_session(_PERCENTILE))
    )

    [grounded] = derive_ledger(refreshed, None).constraints.grounded
    assert (refreshed.domain.data_marks, grounded.status) == (
        DataMarks(searches={_PERCENTILE: "RNASeq"}),
        ConstraintStatus.GROUNDED,
    )


async def test_the_tree_last_answered_keeps_its_mark_beside_the_live_one() -> None:
    hydrated = await refresh_live_strategy_state(
        _state(), _context(_session(_PERCENTILE))
    )

    refreshed = await refresh_live_strategy_state(
        hydrated, _context(_session(_SIMILAR))
    )

    assert refreshed.domain.data_marks == DataMarks(
        searches={_PERCENTILE: "RNASeq", _SIMILAR: "DNA Microarray Assay"}
    )
