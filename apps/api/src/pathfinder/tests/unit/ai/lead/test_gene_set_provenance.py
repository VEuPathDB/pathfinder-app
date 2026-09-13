"""A saved gene set reads its WDK ids from the strategy, never from the model."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.lead import lead_tools
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import workbench
from pathfinder.ai.tools.standalone.workbench_models import GeneSetCreatedResponse
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.strategies.sync_state import ensure_sync_state
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

GENE_IDS = ["PF3D7_0709000", "PF3D7_1133400"]
SET_NAME = "gametocyte secreted candidates v3"
LOCAL_STEP_ID = "step_70056735"
WDK_STEP_ID = 227253270
WDK_STRATEGY_ID = 214618620


@pytest.fixture
def saved(monkeypatch: pytest.MonkeyPatch) -> list[GeneSet]:
    kept: list[GeneSet] = []
    monkeypatch.setattr(workbench, "save_gene_set", kept.append)
    return kept


def _pushed_session() -> StrategySession:
    session = session_with_one_step(step_id=LOCAL_STEP_ID)
    sync_state = ensure_sync_state(session)
    sync_state.wdk_step_ids = {LOCAL_STEP_ID: WDK_STEP_ID}
    sync_state.wdk_strategy_id = WDK_STRATEGY_ID
    return session


def _deps(session: StrategySession | None = None) -> LeadDeps:
    return lead_deps(
        pipeline_state(user_prompt=f"save these genes as {SET_NAME}"),
        strategy_session=session,
    )


async def test_a_save_from_a_local_step_records_the_wdk_step(
    saved: list[GeneSet],
) -> None:
    deps = _deps(_pushed_session())

    await lead_tools.create_workbench_gene_set(
        run_context_for(deps, "call_save"),
        name=SET_NAME,
        gene_ids=GENE_IDS,
        step_id=LOCAL_STEP_ID,
    )

    assert (saved[0].wdk_step_id, saved[0].wdk_strategy_id) == (
        WDK_STEP_ID,
        WDK_STRATEGY_ID,
    )
    assert saved[0].source == "strategy"
    assert saved[0].search_name == "GenesByText"


async def test_a_save_that_names_no_step_records_the_strategy_root(
    saved: list[GeneSet],
) -> None:
    deps = _deps(_pushed_session())

    await lead_tools.create_workbench_gene_set(
        run_context_for(deps, "call_save"),
        name=SET_NAME,
        gene_ids=GENE_IDS,
    )

    assert (saved[0].wdk_step_id, saved[0].wdk_strategy_id) == (
        WDK_STEP_ID,
        WDK_STRATEGY_ID,
    )


async def test_a_thread_with_no_strategy_saves_a_pasted_set(
    saved: list[GeneSet],
) -> None:
    deps = _deps()

    result = await lead_tools.create_workbench_gene_set(
        run_context_for(deps, "call_save"),
        name=SET_NAME,
        gene_ids=GENE_IDS,
    )

    assert saved[0].wdk_step_id is None
    assert saved[0].wdk_strategy_id is None
    assert saved[0].source == "paste"
    created = result.return_value
    assert isinstance(created, GeneSetCreatedResponse)
    assert "no pushed strategy step" in created.message


async def test_a_step_the_strategy_does_not_hold_is_refused(
    saved: list[GeneSet],
) -> None:
    deps = _deps(_pushed_session())

    with pytest.raises(ModelRetry) as raised:
        await lead_tools.create_workbench_gene_set(
            run_context_for(deps, "call_save"),
            name=SET_NAME,
            gene_ids=GENE_IDS,
            step_id="step_999",
        )

    assert LOCAL_STEP_ID in str(raised.value)
    assert saved == []
