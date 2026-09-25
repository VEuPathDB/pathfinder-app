"""The threads fork and revert are measured on, and the WDK push they stand on."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import (
    Conversation,
    ConversationEvent,
    Message,
    ScratchpadNote,
)
from assistant_core.platform import db
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from veupathdb.domain.strategy import walk
from veupathdb.eda import (
    EdaFilter,
    EdaStringSetFilter,
)

from pathfinder.domain.eda_parts import EdaAnalysisState
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.domain.strategy.revision import parse_strategy_ast, without_wdk_ids
from pathfinder.persistence.models import (
    ConversationStrategy,
    StrategyRevision,
    User,
)
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.conversation_analysis import (
    bind_analysis_row,
    bump_analysis_row,
    read_analysis_row,
)
from pathfinder.persistence.repositories.conversation_update import ConversationUpdate
from pathfinder.services.conversations import fork_strategy
from pathfinder.services.strategies import revision_ops
from pathfinder.services.strategies.materialize import MaterializedStrategy
from pathfinder.tests.integration.persistence._strategy_shapes import (
    four_step_ast,
    three_step_ast,
)

THREE_STEPS = {"combine": 15, "protease": 13, "gameto": 14}
FOUR_STEPS = {"orthologs": 16, "combine": 15, "protease": 13, "gameto": 14}
SOURCE_WDK_STRATEGY_ID = 330423363
FIRST_PUSHED_WDK_STRATEGY_ID = 330534153


class _PushedTree(BaseModel):
    """The WDK step ids a stored tree carries, keyed by plan step id."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    wdk_step_ids: dict[str, int] = Field(default_factory=dict, alias="wdkStepIds")


def step_ids_of(strategy_ast: JSONObject) -> dict[str, int]:
    return _PushedTree.model_validate(strategy_ast).wdk_step_ids


def _plan_step_ids_of(strategy_ast: JSONObject) -> list[str]:
    """The tree's own step ids, in push order. Empty when it holds no tree."""
    ast = parse_strategy_ast(strategy_ast)
    if ast is None:
        return []
    return [node.id for node in walk(ast.root)]


@dataclass
class FakePush:
    """Stands in for the WDK push: records the tree, answers with fresh ids.

    WDK answers each push with a strategy and steps of its own, so a second
    push of the same tree never repeats the first push's ids.
    """

    seen: list[JSONObject] = field(default_factory=list)
    pushed_strategy_ids: list[int] = field(default_factory=list)

    async def __call__(
        self,
        *,
        site_id: str,
        conversation_id: UUID,
        name: str,
        strategy_ast: JSONObject,
        record_type: str | None = None,
        step_count: int = 0,
    ) -> MaterializedStrategy:
        del site_id, conversation_id, name, record_type, step_count
        self.seen.append(strategy_ast)
        pushed = len(self.pushed_strategy_ids)
        fresh: JSONObject = {
            key: 7000 + 100 * pushed + offset
            for offset, key in enumerate(_plan_step_ids_of(strategy_ast))
        }
        strategy_id = FIRST_PUSHED_WDK_STRATEGY_ID + pushed
        self.pushed_strategy_ids.append(strategy_id)
        return MaterializedStrategy(
            strategy_ast={**without_wdk_ids(strategy_ast), "wdkStepIds": fresh},
            record_type="transcript",
            step_count=len(fresh),
            wdk_strategy_id=strategy_id,
            created_wdk_strategy=True,
        )


def install_fake_push(monkeypatch: pytest.MonkeyPatch) -> FakePush:
    """Answer every push a branch or a revert makes from the test process."""
    fake = FakePush()
    monkeypatch.setattr(fork_strategy, "materialize_strategy_snapshot", fake)
    monkeypatch.setattr(revision_ops, "materialize_strategy_snapshot", fake)
    return fake


async def seed_user() -> UUID:
    user_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()
    return user_id


async def seed_conversation(
    user_id: UUID,
    *,
    assistant_id: str = "pathfinder",
    name: str = "protease work",
) -> UUID:
    conversation_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(
            Conversation(
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name=name,
                assistant_id=assistant_id,
            ),
        )
        await session.commit()
    return conversation_id


def _user_message_chunk() -> JSONObject:
    return {"type": "user-message", "message": {"id": "", "role": "user", "parts": []}}


def _start_chunk() -> JSONObject:
    return {"type": "start", "messageId": ""}


async def _add_message(
    conversation_id: UUID,
    role: str,
    *,
    chunks: Sequence[JSONObject] = (),
) -> UUID:
    message_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(Message(id=message_id, conversation_id=conversation_id, role=role))
        await session.flush()
        for chunk in chunks:
            session.add(
                ConversationEvent(
                    conversation_id=conversation_id,
                    turn_id=message_id,
                    chunk=chunk,
                ),
            )
        await session.commit()
    return message_id


async def _stamp(conversation_id: UUID, message_id: UUID, *, key: str) -> None:
    """Write the message's own id into the chunk that names it."""
    async with db.async_session_factory() as session:
        row = await session.scalar(
            select(ConversationEvent)
            .where(
                ConversationEvent.conversation_id == conversation_id,
                ConversationEvent.turn_id == message_id,
            )
            .order_by(ConversationEvent.id.desc())
            .limit(1),
        )
        assert row is not None
        chunk = dict(row.chunk)
        if key == "message":
            chunk["message"] = {**chunk["message"], "id": str(message_id)}
        else:
            chunk["messageId"] = str(message_id)
        row.chunk = chunk
        await session.commit()


async def add_user_message(conversation_id: UUID) -> UUID:
    message_id = await _add_message(
        conversation_id,
        "user",
        chunks=[_user_message_chunk()],
    )
    await _stamp(conversation_id, message_id, key="message")
    return message_id


async def add_assistant_message(conversation_id: UUID) -> UUID:
    message_id = await _add_message(
        conversation_id,
        "assistant",
        chunks=[_start_chunk()],
    )
    await _stamp(conversation_id, message_id, key="messageId")
    return message_id


async def write_strategy(conversation_id: UUID, step_ids: dict[str, int]) -> None:
    ast = (
        three_step_ast(dict(step_ids))
        if len(step_ids) == len(THREE_STEPS)
        else four_step_ast(dict(step_ids))
    )
    async with db.async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id,
            ConversationUpdate(
                strategy_ast=ast,
                record_type="transcript",
                step_count=len(step_ids),
                wdk_strategy_id=SOURCE_WDK_STRATEGY_ID,
                wdk_strategy_id_set=True,
            ),
        )
        await session.commit()


@dataclass(frozen=True)
class FourTurns:
    """Two turns that build, then two more that edit the build."""

    conversation_id: UUID
    user_one: UUID
    answer_two: UUID
    user_three: UUID
    answer_four: UUID


async def four_turn_thread(user_id: UUID) -> FourTurns:
    """Turn 2 builds three steps; turn 4 adds an ortholog transform."""
    conversation_id = await seed_conversation(user_id)
    user_one = await add_user_message(conversation_id)
    await write_strategy(conversation_id, THREE_STEPS)
    answer_two = await add_assistant_message(conversation_id)
    user_three = await add_user_message(conversation_id)
    await write_strategy(conversation_id, FOUR_STEPS)
    answer_four = await add_assistant_message(conversation_id)
    return FourTurns(
        conversation_id=conversation_id,
        user_one=user_one,
        answer_two=answer_two,
        user_three=user_three,
        answer_four=answer_four,
    )


def message_ids_in(chunk: JSONObject) -> set[str]:
    """Every message id the chunk spells, however it spells it."""
    identity = _ChunkIdentity.model_validate(chunk)
    found: set[str] = set()
    if identity.message_id is not None:
        found.add(identity.message_id)
    if identity.message is not None and identity.message.id is not None:
        found.add(identity.message.id)
    return found


class _ChunkMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str | None = None


class _ChunkIdentity(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    message_id: str | None = Field(default=None, alias="messageId")
    message: _ChunkMessage | None = None


async def event_count(conversation_id: UUID) -> int:
    async with db.async_session_factory() as session:
        return (
            await session.scalar(
                select(func.count())
                .select_from(ConversationEvent)
                .where(ConversationEvent.conversation_id == conversation_id),
            )
        ) or 0


async def message_roles(conversation_id: UUID) -> list[str]:
    """The thread's messages, oldest first."""
    async with db.async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(Message.role)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at),
                )
            ).scalars(),
        )


async def message_ids(conversation_id: UUID) -> list[str]:
    async with db.async_session_factory() as session:
        return [
            str(mid)
            for mid in (
                await session.execute(
                    select(Message.id)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at),
                )
            ).scalars()
        ]


async def conversation_snapshot(conversation_id: UUID) -> JSONObject:
    """The thread's own row, as comparable values."""
    async with db.async_session_factory() as session:
        row = await session.get(Conversation, conversation_id)
        assert row is not None
        return {
            "name": row.name,
            "assistant_id": row.assistant_id,
            "application_id": row.application_id,
            "parent_conversation_id": str(row.parent_conversation_id),
            "parent_message_id": str(row.parent_message_id),
            "updated_at": row.updated_at.isoformat(),
        }


async def thread_content_snapshot(conversation_id: UUID) -> JSONObject:
    """Every message, chunk, strategy and snapshot row of one thread."""
    async with db.async_session_factory() as session:
        messages = (
            (
                await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conversation_id)
                    .order_by(Message.created_at, Message.id),
                )
            )
            .scalars()
            .all()
        )
        events = (
            (
                await session.execute(
                    select(ConversationEvent)
                    .where(ConversationEvent.conversation_id == conversation_id)
                    .order_by(ConversationEvent.id),
                )
            )
            .scalars()
            .all()
        )
        strategy = await session.get(ConversationStrategy, conversation_id)
        revisions = (
            (
                await session.execute(
                    select(StrategyRevision)
                    .where(StrategyRevision.conversation_id == conversation_id)
                    .order_by(StrategyRevision.id),
                )
            )
            .scalars()
            .all()
        )
    return {
        "messages": [
            [str(row.id), row.role, row.created_at.isoformat()] for row in messages
        ],
        "events": [
            [row.id, str(row.turn_id), str(row.task_id), row.chunk] for row in events
        ],
        "strategy": (
            None
            if strategy is None
            else [
                strategy.record_type,
                strategy.wdk_strategy_id,
                strategy.step_count,
                strategy.strategy_ast,
                strategy.gene_set_id,
                strategy.gene_set_auto_imported,
                list(strategy.imported_saved_strategy_ids),
            ]
        ),
        "revisions": [
            [
                row.id,
                row.revision,
                row.step_count,
                row.wdk_strategy_id,
                str(row.message_id),
                row.strategy_ast,
                row.created_at.isoformat(),
            ]
            for row in revisions
        ],
    }


async def add_note(conversation_id: UUID, title: str) -> str:
    """One scratchpad note, written at the moment it is added."""
    note_id = f"note-{uuid4().hex[:8]}"
    async with db.async_session_factory() as session:
        session.add(
            ScratchpadNote(
                id=note_id,
                conversation_id=conversation_id,
                title=title,
                summary=title,
                body=title,
                tags=[],
                body_tokens=3,
            ),
        )
        await session.commit()
    return note_id


async def note_titles(conversation_id: UUID) -> list[str]:
    async with db.async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(ScratchpadNote.title)
                    .where(ScratchpadNote.conversation_id == conversation_id)
                    .order_by(ScratchpadNote.created_at),
                )
            ).scalars(),
        )


EDA_DATASET = "DS_1234567890"
EDA_SITE = "plasmodb"


def gametocyte_filter(*values: str) -> EdaStringSetFilter:
    """One string-set filter, as a turn would have recorded it."""
    return EdaStringSetFilter(
        entity_id="EUPATH_0000738",
        variable_id="EUPATH_0000054",
        string_set=list(values),
    )


async def add_analysis_state(
    conversation_id: UUID,
    *,
    turn_id: UUID,
    analysis_id: str,
    filters: Sequence[EdaFilter] = (),
    dataset_id: str = EDA_DATASET,
) -> EdaAnalysisState:
    """Record one binding state in the thread's log, as an EDA tool does.

    The part is stamped with its turn's own time, because both the revert cut
    and the branch copy read ``emitted_at``.
    """
    state = EdaAnalysisState(
        site_id=EDA_SITE,
        dataset_id=dataset_id,
        study_id="STUDY_1234567890",
        analysis_id=analysis_id,
        revision=1,
        study_display_name="Gametocyte panel",
        display_name="gametocyte rows",
        num_filters=len(filters),
        num_computations=0,
        filters=[
            one.model_dump(by_alias=True, mode="json", exclude_none=True)
            for one in filters
        ],
        filter_summaries=[f"filter {index}" for index, _ in enumerate(filters)],
        entity_counts=[],
        can_export_rows=True,
    )
    async with db.async_session_factory() as session:
        turn = await session.get(Message, turn_id)
        assert turn is not None
        session.add(
            ConversationEvent(
                conversation_id=conversation_id,
                turn_id=turn_id,
                emitted_at=turn.created_at,
                chunk={
                    "type": "data-eda.analysis-state",
                    "id": analysis_id,
                    "data": state.model_dump(by_alias=True, mode="json"),
                },
            ),
        )
        await session.commit()
    return state


async def bound_analysis(conversation_id: UUID) -> ConversationAnalysisView | None:
    async with db.async_session_factory() as session:
        return await read_analysis_row(session, conversation_id=conversation_id)


async def bind_analysis(
    conversation_id: UUID,
    *,
    analysis_id: str,
    dataset_id: str = EDA_DATASET,
    revision: int = 1,
) -> None:
    """Bind an analysis to a thread and count ``revision`` mutations on it."""
    async with db.async_session_factory() as session:
        await bind_analysis_row(
            session,
            conversation_id=conversation_id,
            site_id=EDA_SITE,
            dataset_id=dataset_id,
            analysis_id=analysis_id,
        )
        for _ in range(revision):
            await bump_analysis_row(session, conversation_id=conversation_id)
        await session.commit()
