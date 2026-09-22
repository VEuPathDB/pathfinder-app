"""A turn that dies tells the researcher what happened, not what raised.

The exception's type and message are a defect report: they belong in the log.
The reply says whether the turn ran and what the researcher can do next.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import BaseModel, ConfigDict, Field

from pathfinder.ai.conversation import turn_failure, turn_runner
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.platform.errors import AppError, ErrorCode

# What a raised defect carries, and what the researcher must never be shown.
_RAISED = "leaf 'step_1a2b3c4d' not found while planning step_9f0e1d2c"
_A_STEP_ID = re.compile(r"\bstep_[0-9a-f]{8}\b")
_APP_ERROR_DETAIL = "This site did not answer. Pick another site or try later."


class _FailureLog(BaseModel):
    """One record the runner wrote about a failed turn."""

    model_config = ConfigDict(extra="ignore")

    event: str
    error_type: str = ""
    error_detail: str = ""


class _ErrorChunk(BaseModel):
    """The live failure chunk, as the writer recorded it."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    error_text: str = Field(alias="errorText")


def _failure_logs(records: list[Any]) -> list[_FailureLog]:
    return [_FailureLog.model_validate(record.msg) for record in records]


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
    """The context of an assistant that holds no strategy, such as site help."""

    cancel_event: asyncio.Event


@dataclass
class _StrategyRuntimeCtx:
    """The context of an assistant that does hold one."""

    cancel_event: asyncio.Event
    strategy_session: object = None


class _RaisingGraph:
    """Fails partway through the stream, the way a driver fails."""

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


def _body(conversation_id: UUID) -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "id": str(conversation_id),
            "trigger": "submit-message",
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "hi"}],
                },
            ],
            "conversationId": str(conversation_id),
            "siteId": "plasmodb",
        },
    )


@pytest.fixture(autouse=True)
def _no_cancel_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _no_poll(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(turn_runner, "watch_for_cancel", _no_poll)


def _writer() -> _StubWriter:
    return _StubWriter(conversation_id=uuid4(), turn_id=uuid4())


async def _drive(exc: Exception, writer: _StubWriter, runtime: Any = None) -> None:
    await turn_runner._drive_graph(
        body=_body(writer.conversation_id),
        graph_input={"turn_message_id": writer.turn_id, "user_id": uuid4()},
        compiled_graph=_RaisingGraph(exc),
        runtime_context=runtime or _StrategyRuntimeCtx(cancel_event=asyncio.Event()),
        writer=writer,
    )


async def _drive_without_a_strategy(exc: Exception, writer: _StubWriter) -> None:
    await _drive(exc, writer, _RuntimeCtx(cancel_event=asyncio.Event()))


def _failure_text(writer: _StubWriter) -> str:
    errors = [
        _ErrorChunk.model_validate(chunk)
        for chunk in writer.chunks
        if chunk.get("type") == "error"
    ]
    return errors[0].error_text


class TestTheTextAGraphFailureLeaves:
    async def test_it_carries_no_exception_class_and_no_raised_message(self) -> None:
        writer = _writer()

        await _drive(RuntimeError(_RAISED), writer)

        text = _failure_text(writer)
        assert "RuntimeError" not in text
        assert _RAISED not in text
        assert _A_STEP_ID.search(text) is None

    async def test_it_says_the_turn_stopped_before_it_answered(self) -> None:
        writer = _writer()

        await _drive(RuntimeError(_RAISED), writer)

        assert _failure_text(writer) == turn_failure.STOPPED_WHILE_RUNNING

    async def test_the_durable_part_carries_the_same_text(self) -> None:
        writer = _writer()

        await _drive(RuntimeError(_RAISED), writer)

        parts = [c for c in writer.chunks if c.get("type") == "data-turn-failed"]
        assert parts[0]["data"] == {"errorText": turn_failure.STOPPED_WHILE_RUNNING}

    async def test_the_log_keeps_the_type_and_the_message(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        writer = _writer()

        with caplog.at_level("ERROR"):
            await _drive(RuntimeError(_RAISED), writer)

        logged = _failure_logs(caplog.records)
        assert [entry.error_type for entry in logged] == ["RuntimeError"]
        assert [entry.error_detail for entry in logged] == [_RAISED]


class TestTheSentencesNameNothingAnAssistantMayNotHave:
    """This module closes the turn of every assistant, strategy or not."""

    def test_neither_sentence_names_a_strategy(self) -> None:
        both = turn_failure.STOPPED_WHILE_RUNNING + turn_failure.STOPPED_BEFORE_IT_RAN

        assert "strategy" not in both.casefold()
        assert "step" not in both.casefold()

    async def test_a_thread_with_no_strategy_reads_the_same_sentence(self) -> None:
        """A help thread holds no strategy, and its crash reads the same way."""
        writer = _writer()

        await _drive_without_a_strategy(RuntimeError(_RAISED), writer)

        assert _failure_text(writer) == turn_failure.STOPPED_WHILE_RUNNING


class TestATypedRefusalKeepsItsOwnSentence:
    async def test_the_app_error_detail_is_what_the_user_reads(self) -> None:
        writer = _writer()

        await _drive(
            AppError(
                code=ErrorCode.SITE_UNAVAILABLE,
                title="Site unavailable",
                detail=_APP_ERROR_DETAIL,
                status=503,
            ),
            writer,
        )

        assert _failure_text(writer) == _APP_ERROR_DETAIL


class TestTheTextASetupFailureLeaves:
    async def test_it_says_nothing_was_changed(self) -> None:
        writer = _writer()

        await turn_failure.write_turn_failure(writer, RuntimeError(_RAISED))

        text = _failure_text(writer)
        assert text == turn_failure.STOPPED_BEFORE_IT_RAN
        assert "nothing was changed" in text

    async def test_it_carries_no_exception_text(self) -> None:
        writer = _writer()

        await turn_failure.write_turn_failure(writer, RuntimeError(_RAISED))

        text = _failure_text(writer)
        assert "RuntimeError" not in text
        assert _RAISED not in text

    async def test_the_log_keeps_the_type_and_the_message(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        writer = _writer()

        with caplog.at_level("ERROR"):
            await turn_failure.write_turn_failure(writer, RuntimeError(_RAISED))

        logged = _failure_logs(caplog.records)
        assert [entry.error_type for entry in logged] == ["RuntimeError"]
        assert [entry.error_detail for entry in logged] == [_RAISED]
