from __future__ import annotations

from typing import NoReturn

import pytest
from veupathdb.errors import WDKError

from strategist.ai.lead import sub_agent_dispatch
from strategist.ai.lead.dispatch_context import agent_deps_for
from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.domain.unread import Unread
from strategist.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

_BUILT = BuildOutcome(pushed_step_ids=["step_a"], wdk_strategy_id=900)
_UNAVAILABLE = WDKError("Service Unavailable", status=503)


async def _unanswered(**_kwargs: object) -> NoReturn:
    raise _UNAVAILABLE


async def test_a_recovery_whose_commit_failed_says_the_strategy_was_not_reread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sub_agent_dispatch, "commit_tree", _unanswered)
    deps = lead_deps(
        pipeline_state("plasmodb"), strategy_session=session_with_one_step("plasmodb")
    )

    outcome = await sub_agent_dispatch._resync_outcome(
        agent_deps_for(deps, call_id="call_recover"), _BUILT
    )

    assert (outcome.pushed_step_ids, outcome.not_read) == (
        ["step_a"],
        Unread(
            reason=(
                "the strategy was not re-read after the recovery: HTTP 503: "
                "VEuPathDB service error: Service Unavailable"
            )
        ),
    )
