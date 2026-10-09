from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.stream_parts.agent_topology import (
    SubAgentCallPayload,
    lead_usage_event,
    sub_agent_call_event,
)
from assistant_core.graph.stream_events import turn_stopped_event, turn_usage_event
from prometheus_client import REGISTRY
from pydantic import BaseModel, SecretStr
from pydantic_ai.ui.vercel_ai.response_types import FinishChunk

from pathfinder.domain.provider_keys import ProviderKeyring
from pathfinder.jobs.turn_metrics import metered_turn
from pathfinder.platform.model_keys import attach_keyring

_LEAD = "openai:probe-lead"
_FRAME = "anthropic:probe-frame"
_HELPER = "openai:probe-helper"


class _ProbeError(RuntimeError):
    pass


class _Sink:
    def __init__(self) -> None:
        self.conversation_id: UUID = uuid4()
        self.turn_id: UUID = uuid4()
        self.chunks: list[dict[str, Any]] = []

    async def write(self, chunk: dict[str, Any]) -> int:
        self.chunks.append(chunk)
        return len(self.chunks)


def _wire(chunk: BaseModel) -> dict[str, Any]:
    return chunk.model_dump(by_alias=True, mode="json", exclude_none=True)


def _sample(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _finished(assistant: str, outcome: str, model: str) -> float:
    return _sample(
        "pathfinder_chat_turns_finished_total",
        {"assistant": assistant, "outcome": outcome, "model": model},
    )


def _tokens(model: str, payer: str) -> float:
    return _sample("pathfinder_model_tokens_total", {"model": model, "payer": payer})


def _cost(model: str, payer: str) -> float:
    return _sample("pathfinder_model_cost_usd_total", {"model": model, "payer": payer})


def _frame_call(
    state: Literal["started", "completed"], tokens: int, cost: str
) -> dict[str, Any]:
    return _wire(
        sub_agent_call_event(
            SubAgentCallPayload(
                tool_call_id="call-frame",
                sub_agent="frame",
                phase="frame",
                state=state,
                model_id=_FRAME,
                tokens=tokens,
                cost_usd=cost,
            ),
        ),
    )


async def test_a_completed_turn_counts_each_model_on_the_key_that_paid() -> None:
    finished = _finished("pathfinder", "completed", _LEAD)
    lead_tokens, lead_cost = _tokens(_LEAD, "deployment"), _cost(_LEAD, "deployment")
    frame_tokens, frame_cost = _tokens(_FRAME, "user"), _cost(_FRAME, "user")
    sink = _Sink()

    async with metered_turn(
        assistant_id="pathfinder", model_id=_LEAD, writer=sink
    ) as writer:
        with attach_keyring(ProviderKeyring(active={"anthropic": SecretStr("k")})):
            for chunk in (
                _wire(lead_usage_event(model_id=_LEAD, tokens=400, cost_usd="0.008")),
                _frame_call("started", 0, "0"),
                _frame_call("completed", 500, "0.01"),
                _wire(lead_usage_event(model_id=_LEAD, tokens=1000, cost_usd="0.02")),
                _wire(turn_usage_event(total_tokens=1500, cost_usd="0.03")),
                _wire(FinishChunk(finish_reason="stop")),
            ):
                await writer.write(chunk)

    assert len(sink.chunks) == 6
    assert _finished("pathfinder", "completed", _LEAD) == finished + 1
    assert _tokens(_LEAD, "deployment") == lead_tokens + 1000
    assert _cost(_LEAD, "deployment") == pytest.approx(lead_cost + 0.02)
    assert _tokens(_FRAME, "user") == frame_tokens + 500
    assert _cost(_FRAME, "user") == pytest.approx(frame_cost + 0.01)


async def test_spend_no_agent_names_is_the_turn_models() -> None:
    tokens, cost = _tokens(_HELPER, "deployment"), _cost(_HELPER, "deployment")
    durations = _sample(
        "pathfinder_chat_turn_duration_seconds_count",
        {"assistant": "site_help", "outcome": "completed"},
    )

    async with metered_turn(
        assistant_id="site_help", model_id=_HELPER, writer=_Sink()
    ) as writer:
        await writer.write(_wire(turn_usage_event(total_tokens=300, cost_usd="0.004")))
        await writer.write(_wire(FinishChunk(finish_reason="stop")))

    assert _tokens(_HELPER, "deployment") == tokens + 300
    assert _cost(_HELPER, "deployment") == pytest.approx(cost + 0.004)
    assert (
        _sample(
            "pathfinder_chat_turn_duration_seconds_count",
            {"assistant": "site_help", "outcome": "completed"},
        )
        == durations + 1
    )


async def test_a_turn_the_user_stopped_counts_as_stopped() -> None:
    before = _finished("pathfinder", "stopped", _LEAD)

    async with metered_turn(
        assistant_id="pathfinder", model_id=_LEAD, writer=_Sink()
    ) as writer:
        await writer.write(_wire(turn_stopped_event()))
        await writer.write(_wire(FinishChunk(finish_reason="other")))

    assert _finished("pathfinder", "stopped", _LEAD) == before + 1


async def test_a_turn_that_ends_on_an_error_counts_as_failed() -> None:
    before = _finished("pathfinder", "failed", _LEAD)

    async with metered_turn(
        assistant_id="pathfinder", model_id=_LEAD, writer=_Sink()
    ) as writer:
        await writer.write(_wire(FinishChunk(finish_reason="error")))

    assert _finished("pathfinder", "failed", _LEAD) == before + 1


async def test_a_turn_that_raises_counts_as_failed_and_still_raises() -> None:
    before = _finished("pathfinder", "failed", _LEAD)

    with pytest.raises(_ProbeError):
        async with metered_turn(
            assistant_id="pathfinder", model_id=_LEAD, writer=_Sink()
        ):
            raise _ProbeError

    assert _finished("pathfinder", "failed", _LEAD) == before + 1
