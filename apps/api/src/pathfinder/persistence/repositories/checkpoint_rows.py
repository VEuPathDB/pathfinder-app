from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from assistant_core.conversation.serde import build_checkpoint_serde
from assistant_core.graph.turn_state import PendingApproval
from pydantic import TypeAdapter
from sqlalchemy import (
    Column,
    ColumnElement,
    DateTime,
    Integer,
    LargeBinary,
    MetaData,
    Select,
    Table,
    Text,
    and_,
    cast,
    delete,
    exists,
    func,
    insert,
    literal,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.rows import rows_changed

__all__ = [
    "CHANNEL_VERSIONS",
    "CHECKPOINT_TABLES",
    "CHECKPOINT_TS",
    "PENDING_APPROVAL_CHANNEL",
    "CheckpointCut",
    "copy_checkpoints",
    "cut_checkpoints",
    "parked_approval",
]

CHECKPOINT_TS = "ts"
CHANNEL_VERSIONS = "channel_versions"
PENDING_APPROVAL_CHANNEL = "pending_approval"

_tables = MetaData()
checkpoints = Table(
    "checkpoints",
    _tables,
    Column("thread_id", Text),
    Column("checkpoint_ns", Text),
    Column("checkpoint_id", Text),
    Column("parent_checkpoint_id", Text),
    Column("type", Text),
    Column("checkpoint", JSONB),
    Column("metadata", JSONB),
)
checkpoint_blobs = Table(
    "checkpoint_blobs",
    _tables,
    Column("thread_id", Text),
    Column("checkpoint_ns", Text),
    Column("channel", Text),
    Column("version", Text),
    Column("type", Text),
    Column("blob", LargeBinary),
)
checkpoint_writes = Table(
    "checkpoint_writes",
    _tables,
    Column("thread_id", Text),
    Column("checkpoint_ns", Text),
    Column("checkpoint_id", Text),
    Column("task_id", Text),
    Column("idx", Integer),
    Column("channel", Text),
    Column("type", Text),
    Column("blob", LargeBinary),
    Column("task_path", Text),
)
CHECKPOINT_TABLES = (checkpoints, checkpoint_blobs, checkpoint_writes)

_APPROVAL: TypeAdapter[PendingApproval | None] = TypeAdapter(PendingApproval | None)
_EMPTY_BLOB = "empty"


@dataclass(frozen=True)
class CheckpointCut:
    writes: int
    checkpoints: int
    blobs: int


def _time_of(table: Table) -> ColumnElement[datetime]:
    return cast(table.c.checkpoint[CHECKPOINT_TS].astext, DateTime(timezone=True))


def _before(table: Table, cutoff: datetime | None) -> ColumnElement[bool]:
    if cutoff is None:
        return literal(value=True)
    return _time_of(table) < cutoff


def _named_by_a_checkpoint_of(thread_id: ColumnElement[str]) -> ColumnElement[bool]:
    named = (
        func.jsonb_each_text(checkpoints.c.checkpoint[CHANNEL_VERSIONS])
        .table_valued("key", "value")
        .alias("named")
    )
    return exists(
        select(literal(1))
        .select_from(checkpoints, named)
        .where(
            checkpoints.c.thread_id == thread_id,
            checkpoints.c.checkpoint_ns == checkpoint_blobs.c.checkpoint_ns,
            named.c.key == checkpoint_blobs.c.channel,
            named.c.value == checkpoint_blobs.c.version,
        )
        .correlate(checkpoint_blobs),
    )


def _copy_into(table: Table, target_thread_id: str) -> tuple[list[str], Select[Any]]:
    return [column.name for column in table.columns], select(
        *(
            literal(target_thread_id) if column.name == "thread_id" else column
            for column in table.columns
        ),
    )


async def copy_checkpoints(
    session: AsyncSession,
    *,
    source_thread_id: str,
    target_thread_id: str,
    cutoff: datetime | None,
) -> None:
    names, rows = _copy_into(checkpoints, target_thread_id)
    await session.execute(
        insert(checkpoints).from_select(
            names,
            rows.where(
                checkpoints.c.thread_id == source_thread_id,
                _before(checkpoints, cutoff),
            ),
        ),
    )
    names, rows = _copy_into(checkpoint_blobs, target_thread_id)
    await session.execute(
        insert(checkpoint_blobs).from_select(
            names,
            rows.where(
                checkpoint_blobs.c.thread_id == source_thread_id,
                _named_by_a_checkpoint_of(literal(target_thread_id)),
            ),
        ),
    )
    names, rows = _copy_into(checkpoint_writes, target_thread_id)
    await session.execute(
        insert(checkpoint_writes).from_select(
            names,
            rows.join(checkpoints, _same_checkpoint(checkpoint_writes)).where(
                checkpoint_writes.c.thread_id == source_thread_id,
                _before(checkpoints, cutoff),
            ),
        ),
    )


def _same_checkpoint(table: Table) -> ColumnElement[bool]:
    return and_(
        checkpoints.c.thread_id == table.c.thread_id,
        checkpoints.c.checkpoint_ns == table.c.checkpoint_ns,
        checkpoints.c.checkpoint_id == table.c.checkpoint_id,
    )


async def cut_checkpoints(
    session: AsyncSession,
    *,
    thread_id: str,
    cutoff: datetime,
) -> CheckpointCut:
    at_or_after = and_(
        checkpoints.c.thread_id == thread_id,
        _time_of(checkpoints) >= cutoff,
    )
    writes = rows_changed(
        await session.execute(
            delete(checkpoint_writes).where(
                exists(
                    select(literal(1))
                    .where(_same_checkpoint(checkpoint_writes), at_or_after)
                    .correlate(checkpoint_writes),
                ),
            ),
        ),
    )
    cut = rows_changed(await session.execute(delete(checkpoints).where(at_or_after)))
    blobs = rows_changed(
        await session.execute(
            delete(checkpoint_blobs).where(
                checkpoint_blobs.c.thread_id == thread_id,
                ~_named_by_a_checkpoint_of(checkpoint_blobs.c.thread_id),
            ),
        ),
    )
    return CheckpointCut(writes=writes, checkpoints=cut, blobs=blobs)


async def parked_approval(
    session: AsyncSession,
    *,
    thread_id: str,
) -> PendingApproval | None:
    latest = (
        select(checkpoints.c.checkpoint_ns, checkpoints.c.checkpoint)
        .where(checkpoints.c.thread_id == thread_id, checkpoints.c.checkpoint_ns == "")
        .order_by(checkpoints.c.checkpoint_id.desc())
        .limit(1)
        .subquery()
    )
    row = (
        await session.execute(
            select(checkpoint_blobs.c.type, checkpoint_blobs.c.blob).join(
                latest,
                and_(
                    checkpoint_blobs.c.thread_id == thread_id,
                    checkpoint_blobs.c.checkpoint_ns == latest.c.checkpoint_ns,
                    checkpoint_blobs.c.channel == PENDING_APPROVAL_CHANNEL,
                    checkpoint_blobs.c.version
                    == latest.c.checkpoint[CHANNEL_VERSIONS][
                        PENDING_APPROVAL_CHANNEL
                    ].astext,
                ),
            ),
        )
    ).one_or_none()
    if row is None or row.type == _EMPTY_BLOB:
        return None
    return _APPROVAL.validate_python(
        build_checkpoint_serde().loads_typed((row.type, bytes(row.blob))),
    )
