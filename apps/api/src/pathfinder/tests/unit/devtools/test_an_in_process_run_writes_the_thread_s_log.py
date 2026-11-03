from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation import event_writer
from assistant_core.conversation.event_writer import ChatWriter
from assistant_core.platform.types import JSONObject
from procrastinate.testing import InMemoryConnector

from pathfinder.devtools import chat
from pathfinder.devtools.capture import RunCapture
from pathfinder.devtools.gates import user_body
from pathfinder.jobs.app import procrastinate_app

_SITE = "plasmodb"
_FIRST_LOG_ID = 41


@asynccontextmanager
async def _no_resource(*_args: object, **_kwargs: object) -> AsyncGenerator[None]:
    yield None


class _Spec:
    def build_graph(self, _saver: object) -> None:
        return None


async def _resolve(_conversation_id: UUID, _assistant: str | None) -> _Spec:
    return _Spec()


@pytest.fixture
def in_memory_jobs() -> Iterator[None]:
    original = procrastinate_app.connector
    original_manager = procrastinate_app.job_manager.connector
    connector = InMemoryConnector()
    procrastinate_app.connector = connector
    procrastinate_app.job_manager.connector = connector
    try:
        yield
    finally:
        procrastinate_app.connector = original
        procrastinate_app.job_manager.connector = original_manager


@pytest.mark.usefixtures("in_memory_jobs")
async def test_each_chunk_reaches_the_capture_and_the_log(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    conversation_id, turn_id = uuid4(), uuid4()
    logged: list[tuple[UUID, UUID | None, JSONObject]] = []
    written: list[int] = []

    async def _append(
        *, conversation_id: UUID, chunk: JSONObject, turn_id: UUID | None = None
    ) -> int:
        logged.append((conversation_id, turn_id, chunk))
        return _FIRST_LOG_ID + len(logged) - 1

    async def _turn(*, writer: ChatWriter, **_kwargs: object) -> None:
        written.append(await writer.write({"type": "start", "messageId": "m"}))
        written.append(
            await writer.write({"type": "text-delta", "id": "t", "delta": "hi"})
        )

    monkeypatch.setattr(event_writer, "append_chunk", _append)
    monkeypatch.setattr(chat, "resolve_run_assistant", _resolve)
    monkeypatch.setattr(chat, "lifespan_checkpointer", _no_resource)
    monkeypatch.setattr(chat, "lifespan_memory_store", _no_resource)
    monkeypatch.setattr(chat, "run_turn", _turn)
    args = chat.parse_run_args(
        ["hi", "--site", _SITE, "--mock", "--run-dir", str(tmp_path)]
    ).model_copy(update={"conversation_id": conversation_id})
    capture = RunCapture(
        conversation_id=conversation_id, turn_id=turn_id, run_dir=tmp_path, quiet=True
    )

    await chat._exec_one(
        args,
        capture,
        user_body(chat._body_ctx(args), message_id=turn_id, text="hi", files=[]),
        settings_url="postgresql://unused",
        wdk_token=None,
    )

    assert [(c, t, chunk["type"]) for c, t, chunk in logged] == [
        (conversation_id, turn_id, "start"),
        (conversation_id, turn_id, "text-delta"),
    ]
    assert written == [_FIRST_LOG_ID, _FIRST_LOG_ID + 1]
    assert capture.assistant_text() == "hi"
