"""The in-process debugger opens the job queue a strategy write defers onto."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from assistant_core.platform.db import async_session_factory
from procrastinate import types
from procrastinate.connector import Pool
from procrastinate.exceptions import AppNotOpen
from procrastinate.testing import InMemoryConnector, JobRow
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart, UIMessage

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.devtools import chat
from pathfinder.devtools.capture import RunCapture
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.jobs.app import procrastinate_app
from pathfinder.jobs.tasks import ensure_registered
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.gene_set_refresh import (
    GENE_SET_REFRESH_TASK,
    defer_the_gene_set_refresh,
)

_SITE = "plasmodb"


class _PooledConnector(InMemoryConnector):
    """Refuses a defer while the app is closed, as the psycopg connector does."""

    opened = False

    async def open_async(self, pool: Pool | None = None) -> None:
        await super().open_async(pool)
        self.opened = True

    async def close_async(self) -> None:
        await super().close_async()
        self.opened = False

    async def defer_jobs_all(self, jobs: list[types.JobToDefer]) -> list[JobRow]:
        if not self.opened:
            raise AppNotOpen
        return await super().defer_jobs_all(jobs)


@pytest.fixture
def pooled_jobs() -> Iterator[_PooledConnector]:
    original = procrastinate_app.connector
    original_jm = procrastinate_app.job_manager.connector
    connector = _PooledConnector()
    procrastinate_app.connector = connector
    procrastinate_app.job_manager.connector = connector
    ensure_registered()
    try:
        yield connector
    finally:
        procrastinate_app.connector = original
        procrastinate_app.job_manager.connector = original_jm


@asynccontextmanager
async def _no_resource(*_args: object, **_kwargs: object) -> AsyncGenerator[None]:
    yield None


class _Spec:
    def build_graph(self, _saver: object) -> None:
        return None


def _body(conversation_id: UUID) -> ChatRequestBody:
    message_id = str(uuid4())
    return ChatRequestBody(
        id=message_id,
        messages=[UIMessage(id=message_id, role="user", parts=[TextUIPart(text="hi")])],
        conversation_id=conversation_id,
        site_id=_SITE,
    )


async def test_a_strategy_write_in_the_turn_defers_the_refresh(
    monkeypatch: pytest.MonkeyPatch,
    pooled_jobs: _PooledConnector,
    tmp_path: Path,
) -> None:
    """The turn's strategy write reaches the queue while the debugger holds it open."""
    conversation_id = uuid4()

    async def _resolve(_conversation_id: UUID, _assistant: str | None) -> _Spec:
        return _Spec()

    async def _turn_writes_the_strategy(**_kwargs: object) -> None:
        await defer_the_gene_set_refresh(
            StrategyMutationContext(
                site_id=_SITE,
                strategy_session=StrategySession(site_id=_SITE),
                conversation_id=conversation_id,
                db_session_factory=async_session_factory,
            )
        )

    monkeypatch.setattr(chat, "resolve_run_assistant", _resolve)
    monkeypatch.setattr(chat, "lifespan_checkpointer", _no_resource)
    monkeypatch.setattr(chat, "lifespan_memory_store", _no_resource)
    monkeypatch.setattr(chat, "run_turn", _turn_writes_the_strategy)
    args = chat.parse_run_args(
        ["hi", "--site", _SITE, "--mock", "--run-dir", str(tmp_path)]
    )

    await chat._exec_one(
        args,
        RunCapture(
            conversation_id=conversation_id,
            turn_id=uuid4(),
            run_dir=tmp_path,
            quiet=True,
        ),
        _body(conversation_id),
        settings_url="postgresql://unused",
        wdk_token=None,
    )

    refreshes = [
        (job["lock"], job["args"]["payload"]["conversation_id"])
        for job in pooled_jobs.jobs.values()
        if job["task_name"] == GENE_SET_REFRESH_TASK
    ]
    assert refreshes == [(f"gene-set-refresh:{conversation_id}", str(conversation_id))]
    assert pooled_jobs.opened is False
