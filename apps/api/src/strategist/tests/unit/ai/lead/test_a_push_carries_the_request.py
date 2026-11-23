"""Every strategy write a turn makes carries the request the thread answers.

A strategy the thread has not titled yet is pushed under that request, the
same text the web shows for an untitled thread.
"""

from __future__ import annotations

from typing import Any

import pytest

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead import sub_agent_dispatch
from strategist.ai.lead.dispatch_context import agent_deps_for
from strategist.ai.tools.standalone import eda_step
from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.services.strategies.commit_tree import CommittedTree
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

_REQUEST = "Find genes upregulated 24 hours post blood meal"


def test_a_sub_agents_writes_carry_the_request() -> None:
    deps = lead_deps(pipeline_state(user_prompt=_REQUEST))

    assert (
        agent_deps_for(deps, call_id="call_test").to_strategy_context().user_prompt
        == _REQUEST
    )


def test_a_later_turn_carries_the_threads_original_request() -> None:
    state = pipeline_state(
        user_prompt="Use the 24 hour time point only",
        domain=StrategyDomainState(original_request=_REQUEST),
    )

    assert agent_deps_for(
        lead_deps(state), call_id="call_test"
    ).to_strategy_context().user_prompt == (_REQUEST)


def test_an_eda_step_carries_the_request() -> None:
    ctx = run_context_for(lead_deps(pipeline_state(user_prompt=_REQUEST)))

    assert eda_step._strategy_context(ctx, None, {}).user_prompt == _REQUEST


async def test_a_recovery_resync_carries_the_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    names: list[str] = []

    async def _commit(**kwargs: Any) -> CommittedTree:
        names.append(kwargs["target"].name)
        return CommittedTree(
            pushed=[],
            failures=[],
            drafts={},
            skipped=[],
            sync=None,
            record_type=None,
            held={},
            put=True,
        )

    monkeypatch.setattr(sub_agent_dispatch, "commit_tree", _commit)
    deps = lead_deps(
        pipeline_state(user_prompt=_REQUEST),
        strategy_session=session_with_one_step(name=""),
    )

    await sub_agent_dispatch._resync_outcome(
        agent_deps_for(deps, call_id="call_test"), BuildOutcome()
    )

    assert names == [_REQUEST]
