from __future__ import annotations

from collections.abc import AsyncIterator
from typing import NoReturn

import pytest
from pydantic_ai.exceptions import ModelAPIError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits

from pathfinder.ai.explore.explore_agent import ExploreAgent
from pathfinder.ai.graph import explore_node
from pathfinder.ai.graph._lead_model import LeadModelContext
from pathfinder.ai.lead.turn_budget import lead_turn_budget_message
from pathfinder.tests._support.explore_turns import (
    EXPLORE_PROMPT,
    ExploreDoubles,
    domain_of,
    explore_state,
    install_explore_doubles,
    run_explore,
    update_of,
)

_ONE_CALL = UsageLimits(request_limit=1)
_UNAVAILABLE = "function:unavailable"
_UNAVAILABLE_MESSAGE = "the provider is unavailable"
_ERROR_STOP = (
    "I stopped this turn on an error I could not recover from; what it answered "
    "is shown beside this reply. Send the message again and I will start over "
    "from it."
)


@pytest.fixture
def doubles(monkeypatch: pytest.MonkeyPatch) -> ExploreDoubles:
    return install_explore_doubles(monkeypatch)


def _unavailable(messages: list[ModelMessage], info: AgentInfo) -> NoReturn:
    del messages, info
    raise ModelAPIError(_UNAVAILABLE, _UNAVAILABLE_MESSAGE)


async def _unavailable_stream(
    messages: list[ModelMessage], info: AgentInfo
) -> AsyncIterator[str]:
    _unavailable(messages, info)
    yield ""


def _failing_model(agent: ExploreAgent, **_settings: object) -> LeadModelContext:
    model = FunctionModel(_unavailable, stream_function=_unavailable_stream)
    return LeadModelContext(
        override=agent.override(model=model),
        model_id=_UNAVAILABLE,
        reasoning_effort=None,
    )


async def test_an_explore_turn_charges_its_spend(doubles: ExploreDoubles) -> None:
    state = explore_state(EXPLORE_PROMPT, turn_total_tokens=10)
    command = await run_explore(state)

    update = update_of(command)
    [usage] = [c["data"] for c in doubles.of_type("data-turn-usage")]
    assert doubles.charges == [(state.user_id, update["turn_total_tokens"] - 10)]
    assert update["turn_total_tokens"] > 10
    assert usage["totalTokens"] == update["turn_total_tokens"]


async def test_an_explore_turn_shows_its_model_usage_card(
    doubles: ExploreDoubles,
) -> None:
    command = await run_explore(explore_state(EXPLORE_PROMPT, turn_total_tokens=10))

    [card] = doubles.of_type("data-lead-usage")
    assert card["id"] == "lead-usage"
    assert card["data"]["modelId"] == "mock:explore"
    assert card["data"]["tokens"] == update_of(command)["turn_total_tokens"] - 10
    assert card["data"]["costUsd"] == str(update_of(command)["turn_total_cost_usd"])


async def test_a_turn_at_its_budget_says_it_stopped(
    doubles: ExploreDoubles, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(explore_node, "lead_usage_limits", lambda: _ONE_CALL)

    command = await run_explore(explore_state(EXPLORE_PROMPT))

    [reply] = doubles.replies()
    budget = lead_turn_budget_message(RunUsage(requests=1), _ONE_CALL)
    assert reply.endswith(budget)
    assert domain_of(command).exchanges[-1].reply == reply
    assert "pending_approval" not in update_of(command)


async def test_a_run_error_says_the_turn_stopped_on_it(
    doubles: ExploreDoubles, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(explore_node, "resolve_explore_model_context", _failing_model)

    command = await run_explore(explore_state(EXPLORE_PROMPT))

    assert [chunk["type"] for chunk in doubles.of_type("error")] == ["error"]
    assert doubles.replies() == [_ERROR_STOP]
    assert domain_of(command).exchanges[-1].reply == _ERROR_STOP
