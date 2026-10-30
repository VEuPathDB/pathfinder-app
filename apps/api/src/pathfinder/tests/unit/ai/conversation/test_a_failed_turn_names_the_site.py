from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.spec import turn_input
from langgraph.graph import START, StateGraph
from pydantic import BaseModel, ConfigDict, Field

from pathfinder.ai.conversation import turn_failure, turn_runner
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.ai.graph.lead_node import make_lead_node
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.lead_agent import LeadAgent
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.site_failures import (
    failed_read,
    refused,
    timed_out,
    unavailable,
)

_PLASMODB_STOPPED_IT = (
    "PlasmoDB did not answer, so this turn stopped and nothing was changed. "
    "Send the message again."
)


class _ErrorChunk(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    error_text: str = Field(alias="errorText")


@dataclass
class _StubWriter:
    conversation_id: UUID
    turn_id: UUID
    chunks: list[dict[str, Any]] = field(default_factory=list)

    async def write(self, chunk: dict[str, Any]) -> int:
        self.chunks.append(chunk)
        return len(self.chunks)


@dataclass
class _RuntimeCtx:
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    strategy_session: object = None


class _RaisingGraph:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc

    def astream(
        self,
        graph_input: dict[str, Any],
        config: dict[str, Any],
        context: Any,
        stream_mode: str,
    ) -> AsyncIterator[Any]:
        del graph_input, config, context, stream_mode
        return self._iter()

    async def _iter(self) -> AsyncIterator[Any]:
        yield {"chunk": {"type": "text-delta", "id": "t", "delta": "Look"}}
        raise self.exc


@pytest.fixture(autouse=True)
def _no_cancel_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_poll(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(turn_runner, "watch_for_cancel", _no_poll)


def _writer() -> _StubWriter:
    return _StubWriter(conversation_id=uuid4(), turn_id=uuid4())


def _body(conversation_id: UUID) -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "id": str(conversation_id),
            "trigger": "submit-message",
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "Find gametocyte genes"}],
                },
            ],
            "conversationId": str(conversation_id),
            "siteId": "plasmodb",
        },
    )


def _failure_text(writer: _StubWriter) -> str:
    errors = [
        _ErrorChunk.model_validate(chunk)
        for chunk in writer.chunks
        if chunk.get("type") == "error"
    ]
    return errors[0].error_text


def _no_agent() -> LeadAgent:
    msg = "the turn reached the Lead"
    raise AssertionError(msg)


def _never_finalized(state: PipelineState) -> dict[str, Any]:
    msg = f"the turn of {state.conversation_id} reached finalize_turn"
    raise AssertionError(msg)


def _graph_whose_pre_turn_raises(exc: Exception) -> Any:
    async def _pre_turn(state: PipelineState, context: Context) -> PipelineState:
        del state, context
        raise exc

    graph: StateGraph[PipelineState, Context, PipelineState, PipelineState] = (
        StateGraph(PipelineState, context_schema=Context)
    )
    graph.add_node("lead", make_lead_node(pre_turn=_pre_turn, build_agent=_no_agent))
    graph.add_node("finalize_turn", _never_finalized)
    graph.add_edge(START, "lead")
    return graph.compile()


async def _drive_pre_turn_failure(exc: Exception, writer: _StubWriter) -> None:
    state = PipelineState(
        conversation_id=writer.conversation_id,
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="Find gametocyte genes",
        turn_message_id=writer.turn_id,
    )
    await turn_runner._drive_graph(
        body=_body(writer.conversation_id),
        graph_input=turn_input(state),
        compiled_graph=_graph_whose_pre_turn_raises(exc),
        runtime_context=Context(
            site_id="plasmodb",
            user_id=state.user_id,
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        ),
        writer=writer,
    )


async def _drive_graph_failure(exc: Exception, writer: _StubWriter) -> None:
    await turn_runner._drive_graph(
        body=_body(writer.conversation_id),
        graph_input={"turn_message_id": writer.turn_id, "user_id": uuid4()},
        compiled_graph=_RaisingGraph(exc),
        runtime_context=_RuntimeCtx(),
        writer=writer,
    )


async def test_a_503_from_the_pre_turn_read_names_the_site_and_changes_nothing() -> (
    None
):
    writer = _writer()

    await _drive_pre_turn_failure(await failed_read("plasmodb", unavailable), writer)

    assert _failure_text(writer) == _PLASMODB_STOPPED_IT


async def test_a_refusal_from_the_pre_turn_read_keeps_the_generic_text() -> None:
    writer = _writer()

    await _drive_pre_turn_failure(await failed_read("plasmodb", refused), writer)

    assert _failure_text(writer) == turn_failure.STOPPED_WHILE_RUNNING


async def test_a_timeout_to_orthomcl_during_the_turn_names_orthomcl() -> None:
    writer = _writer()

    await _drive_graph_failure(await failed_read("orthomcl", timed_out), writer)

    assert _failure_text(writer) == (
        "OrthoMCL did not answer, so this turn stopped before it could answer. "
        "Ask again."
    )


async def test_the_durable_part_carries_the_site_sentence() -> None:
    writer = _writer()

    await _drive_graph_failure(await failed_read("orthomcl", timed_out), writer)

    parts = [c for c in writer.chunks if c.get("type") == "data-turn-failed"]
    assert parts[0]["data"] == {"errorText": _failure_text(writer)}
    assert _failure_text(writer).startswith("OrthoMCL did not answer")


async def test_a_setup_step_that_reads_a_dead_site_names_it() -> None:
    writer = _writer()

    await turn_failure.write_turn_failure(
        writer, await failed_read("plasmodb", unavailable)
    )

    assert _failure_text(writer) == _PLASMODB_STOPPED_IT


async def test_an_exception_that_is_no_site_failure_keeps_the_generic_text() -> None:
    writer = _writer()

    await _drive_graph_failure(RuntimeError("leaf not found"), writer)

    assert _failure_text(writer) == turn_failure.STOPPED_WHILE_RUNNING


async def test_a_refusal_during_the_turn_keeps_the_generic_text() -> None:
    writer = _writer()

    await _drive_graph_failure(await failed_read("plasmodb", refused), writer)

    assert _failure_text(writer) == turn_failure.STOPPED_WHILE_RUNNING
