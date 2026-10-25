from __future__ import annotations

import operator
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from typing import Annotated, TypedDict
from uuid import uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.graph.turn_state import TurnState
from assistant_core.platform import db
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select, text

from pathfinder.persistence.repositories.checkpoint_rows import (
    CHANNEL_VERSIONS,
    CHECKPOINT_TABLES,
    CHECKPOINT_TS,
    PENDING_APPROVAL_CHANNEL,
    checkpoint_blobs,
    checkpoints,
)
from pathfinder.platform.config import get_settings

_COLUMNS = text(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_schema = current_schema() AND table_name = :table "
    "ORDER BY ordinal_position",
)


class _Findings(TypedDict):
    findings: Annotated[list[str], operator.add]
    label: str


def _note(state: _Findings) -> dict[str, list[str]]:
    return {"findings": [state["label"]]}


@pytest.fixture
async def saver(patch_app_db_engine: None) -> AsyncIterator[AsyncPostgresSaver]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url) as opened:
        yield opened


async def test_the_installed_checkpointer_creates_exactly_the_named_columns(
    saver: AsyncPostgresSaver,
) -> None:
    del saver
    async with db.async_session_factory() as session:
        created = {
            table.name: [
                row.column_name
                for row in await session.execute(_COLUMNS, {"table": table.name})
            ]
            for table in CHECKPOINT_TABLES
        }

    assert created == {
        table.name: [column.name for column in table.columns]
        for table in CHECKPOINT_TABLES
    }


async def test_a_graph_run_writes_the_time_and_the_blob_names_surgery_reads(
    saver: AsyncPostgresSaver,
) -> None:
    graph = (
        StateGraph(_Findings)
        .add_node("note", _note)
        .add_edge(START, "note")
        .add_edge("note", END)
        .compile(checkpointer=saver)
    )
    thread_id = str(uuid4())
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    await graph.ainvoke(_Findings(findings=[], label="gametocyte"), config)
    await graph.ainvoke(_Findings(findings=[], label="vivax"), config)
    saved = {
        held.checkpoint["id"]: held.checkpoint async for held in saver.alist(config)
    }

    async with db.async_session_factory() as session:
        rows = (
            await session.execute(
                select(checkpoints.c.checkpoint_id, checkpoints.c.checkpoint).where(
                    checkpoints.c.thread_id == thread_id,
                ),
            )
        ).all()
        blobs = {
            (row.channel, row.version)
            for row in await session.execute(
                select(checkpoint_blobs.c.channel, checkpoint_blobs.c.version).where(
                    checkpoint_blobs.c.thread_id == thread_id,
                ),
            )
        }

    stored = {row.checkpoint_id: row.checkpoint for row in rows}
    assert {key: value[CHECKPOINT_TS] for key, value in stored.items()} == {
        key: value["ts"] for key, value in saved.items()
    }
    assert {
        datetime.fromisoformat(value[CHECKPOINT_TS]).utcoffset()
        for value in stored.values()
    } == {timedelta(0)}
    named = {
        pair for value in stored.values() for pair in value[CHANNEL_VERSIONS].items()
    }
    assert blobs <= named
    assert ("findings", stored[max(stored)][CHANNEL_VERSIONS]["findings"]) in blobs
    assert PENDING_APPROVAL_CHANNEL in TurnState.model_fields
