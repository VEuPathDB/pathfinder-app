"""Every strategy write a turn makes carries the researcher's request of that turn.

A strategy the thread has not titled yet is pushed under that request.
"""

from __future__ import annotations

from typing import Any

import pytest

from pathfinder.ai.lead import sub_agent_dispatch
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

_REQUEST = "Find genes upregulated 24 hours post blood meal"


def test_a_sub_agents_writes_carry_the_request() -> None:
    deps = lead_deps(pipeline_state(user_prompt=_REQUEST))

    assert agent_deps_for(deps).to_strategy_context().user_prompt == _REQUEST


def test_an_eda_step_carries_the_request() -> None:
    ctx = run_context_for(lead_deps(pipeline_state(user_prompt=_REQUEST)))

    assert eda_step._strategy_context(ctx, None).user_prompt == _REQUEST


async def test_a_recovery_resync_carries_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[str] = []

    async def _sync(**kwargs: Any) -> SyncResult:
        requests.append(kwargs["user_prompt"])
        return SyncResult(
            wdk_strategy_id=330679883,
            wdk_url=None,
            root_step_id=440537303,
            counts={},
            root_count=None,
            zero_step_ids=[],
            step_count=1,
        )

    monkeypatch.setattr(sub_agent_dispatch, "sync_strategy_for_site", _sync)
    deps = lead_deps(
        pipeline_state(user_prompt=_REQUEST), strategy_session=session_with_one_step()
    )

    await sub_agent_dispatch._resync_outcome(agent_deps_for(deps), BuildOutcome())

    assert requests == [_REQUEST]
