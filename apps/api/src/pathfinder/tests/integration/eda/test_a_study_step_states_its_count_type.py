"""The E2 study step, checked against the live plasmodb study, states the sense
count column by the name the study gives it.

Gated on WDK_TEST_TOKEN, or WDK_TEST_EMAIL/WDK_TEST_PASSWORD (skipped unset).
"""

from __future__ import annotations

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy import flatten_tree

from pathfinder.ai.tools.standalone.strategy_graph import (
    StudyStepCheck,
    check_study_step,
)
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_words import StampedKind
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context, summary_of
from pathfinder.tests.unit.domain.strategy._analysis import (
    COMPUTE_SEARCH,
    E2_STEP,
    e2_step,
)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]


def _session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("g1", "Heat shock DHC", "plasmodb")
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(e2_step()))
    graph.recompute_roots()
    graph.note_analysis_kinds(
        {E2_STEP: StampedKind(search_name=COMPUTE_SEARCH, kind=AnalysisKind.COMPUTE)}
    )
    session.graph = graph
    session.sync_state = WDKSyncState(step_counts={E2_STEP: 201})
    return session


async def test_the_e2_step_names_the_sense_count_column(
    require_wdk_creds: str,
) -> None:
    handle = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        answer = await check_study_step(
            agent_run_context(strategy_session=_session()), E2_STEP
        )
    finally:
        veupathdb_auth_token_ctx.reset(handle)

    assert returned(answer, StudyStepCheck).value_variable == "Sense Count"
    assert summary_of(answer).data["summary"] == (
        "201 records at 2-fold and p 0.05, DESeq on Sense Count: genes that "
        "differ between wildtype and delta-DHC mutant"
    )
