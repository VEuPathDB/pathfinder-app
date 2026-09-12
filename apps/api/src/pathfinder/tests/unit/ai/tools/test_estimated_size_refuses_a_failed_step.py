"""A step WDK refused has no count to report, so the size tool names the refusal.

Reading the size of the WDK step id a failed edit left behind answers the count
of the search WDK still runs, which is the search the user asked to replace.
"""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb_mcp import ToolErrorPayload
from veupathdb_mcp.wdk import StepCountResult

from pathfinder.ai.tools.standalone import execution
from pathfinder.ai.tools.standalone._result_models import EstimatedSizeResult
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_STEP_ID = "step_7c2e770b"
_WDK_STEP_ID = 440432473
_REFUSAL = (
    "PUT /users/1216062453/steps/440432473/search-config -> HTTP 422 (SEMANTIC): "
    "profileset_generic: Invalid value 'Pfal3D7 Gametocyte time course'."
)


@pytest.fixture
def stale_size(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _old_count(*_args: Any, **_kwargs: Any) -> StepCountResult:
        return StepCountResult(step_id=_WDK_STEP_ID, count=1282)

    monkeypatch.setattr(execution, "get_estimated_size_for_site", _old_count)


@pytest.mark.usefixtures("stale_size")
async def test_a_step_with_a_push_error_reports_the_error_not_a_count() -> None:
    ctx = agent_run_context()
    session = StrategySession(site_id="plasmodb")
    session.sync_state = WDKSyncState(
        wdk_step_ids={_STEP_ID: _WDK_STEP_ID},
        wdk_push_errors={_STEP_ID: _REFUSAL},
    )
    ctx.deps.strategy_session = session

    payload = returned(
        await execution.get_estimated_size(ctx, _WDK_STEP_ID), ToolErrorPayload
    )

    assert payload.ok is False
    assert "Invalid value" in str(payload.model_dump())


@pytest.mark.usefixtures("stale_size")
async def test_a_step_that_reached_wdk_still_reports_its_count() -> None:
    ctx = agent_run_context()
    session = StrategySession(site_id="plasmodb")
    session.sync_state = WDKSyncState(wdk_step_ids={_STEP_ID: _WDK_STEP_ID})
    ctx.deps.strategy_session = session

    answer = await execution.get_estimated_size(ctx, _WDK_STEP_ID)

    assert returned(answer, EstimatedSizeResult).count == 1282
