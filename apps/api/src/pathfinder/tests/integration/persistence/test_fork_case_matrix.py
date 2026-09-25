"""The branch case matrix: F1 to F9 of the thread-surgery invariants.

Each test names the invariant it holds. The invariants are written down in
``docs/knowledge/conventions/thread-surgery-invariants.md``.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.memory.schemas import MemoryValue
from assistant_core.memory.store import MemoryStore
from assistant_core.persistence.models import (
    BackgroundTask,
    Conversation,
    ConversationEvent,
)
from assistant_core.platform import db
from langgraph.runtime import Runtime
from sqlalchemy import select, text

from pathfinder.ai.graph import _lead_turn
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.persistence.models import (
    ConversationStrategy,
    GeneSetRow,
)
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.tests.integration.persistence._fake_eda import install_fake_eda
from pathfinder.tests.integration.persistence._thread_surgery import (
    EDA_DATASET,
    FOUR_STEPS,
    SOURCE_WDK_STRATEGY_ID,
    THREE_STEPS,
    FakePush,
    add_analysis_state,
    add_assistant_message,
    add_note,
    add_user_message,
    bind_analysis,
    bound_analysis,
    conversation_snapshot,
    four_turn_thread,
    gametocyte_filter,
    install_fake_push,
    message_ids,
    message_ids_in,
    message_roles,
    note_titles,
    seed_conversation,
    seed_user,
    step_ids_of,
    thread_content_snapshot,
    write_strategy,
)


@pytest.fixture(scope="module", autouse=True)
async def _langgraph_checkpoint_tables(
    patch_app_db_engine: None,
) -> AsyncIterator[None]:
    del patch_app_db_engine
    async with lifespan_checkpointer(get_settings().database_url):
        yield


@pytest.fixture(autouse=True)
async def _truncate_langgraph_tables() -> AsyncIterator[None]:
    yield
    async with db.async_session_factory() as session:
        await session.execute(
            text(
                "TRUNCATE TABLE checkpoints, checkpoint_blobs, "
                "checkpoint_writes RESTART IDENTITY",
            ),
        )
        await session.commit()


async def _fork(
    *,
    source_conversation_id: UUID,
    from_message_id: UUID,
    user_id: UUID,
) -> UUID:
    async with db.async_session_factory() as session:
        fork = await fork_conversation(
            session,
            source_conversation_id=source_conversation_id,
            from_message_id=from_message_id,
            user_id=user_id,
        )
        await session.commit()
        return fork.id


async def _strategy_of(conversation_id: UUID) -> ConversationStrategy | None:
    async with db.async_session_factory() as session:
        return await session.get(ConversationStrategy, conversation_id)


# F1: a fork copies exactly the turns at or before the anchor.


async def test_f1_a_branch_copies_exactly_the_turns_at_or_before_the_anchor(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    at_answer_two = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_two,
        user_id=user_id,
    )
    at_user_three = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.user_three,
        user_id=user_id,
    )
    at_answer_four = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )

    assert await message_roles(at_answer_two) == ["user", "assistant"]
    assert await message_roles(at_user_three) == ["user", "assistant", "user"]
    assert await message_roles(at_answer_four) == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert await message_roles(thread.conversation_id) == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


async def test_f1_a_branch_copies_only_the_notes_written_by_its_own_turns(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A note is a turn's artifact, so a branch holds only its own turns'."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    conversation_id = await seed_conversation(user_id)
    await add_user_message(conversation_id)
    await write_strategy(conversation_id, THREE_STEPS)
    await add_note(conversation_id, "proteases shortlisted")
    answer_two = await add_assistant_message(conversation_id)
    await add_user_message(conversation_id)
    await write_strategy(conversation_id, FOUR_STEPS)
    await add_note(conversation_id, "vivax orthologs added")
    await add_assistant_message(conversation_id)

    fork_id = await _fork(
        source_conversation_id=conversation_id,
        from_message_id=answer_two,
        user_id=user_id,
    )

    assert await note_titles(fork_id) == ["proteases shortlisted"]
    assert await note_titles(conversation_id) == [
        "proteases shortlisted",
        "vivax orthologs added",
    ]


# F3: the fork's strategy is the anchor's revision as a new WDK strategy.


async def test_f3_a_branch_owns_a_new_wdk_strategy_with_step_ids_of_its_own(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A later turn edited the tree, so the branch must not read the latest."""
    del patch_app_db_engine, db_cleaner
    push = install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    fork_id = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_two,
        user_id=user_id,
    )

    branch = await _strategy_of(fork_id)
    parent = await _strategy_of(thread.conversation_id)
    assert branch is not None
    assert parent is not None
    assert set(step_ids_of(branch.strategy_ast)) == set(THREE_STEPS)
    assert branch.wdk_strategy_id == push.pushed_strategy_ids[0]
    assert branch.wdk_strategy_id != parent.wdk_strategy_id
    assert set(step_ids_of(branch.strategy_ast).values()).isdisjoint(
        step_ids_of(parent.strategy_ast).values(),
    )
    assert parent.wdk_strategy_id == SOURCE_WDK_STRATEGY_ID
    assert set(step_ids_of(parent.strategy_ast)) == set(FOUR_STEPS)


# F4: a fork of a fork obeys F1 to F3 against ITS parent.


async def test_f4_a_branch_of_a_branch_obeys_f1_to_f3_against_its_own_parent(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    push = install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    first = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )
    first_ids = await message_ids(first)
    second = await _fork(
        source_conversation_id=first,
        from_message_id=UUID(first_ids[1]),
        user_id=user_id,
    )

    assert await message_roles(first) == ["user", "assistant", "user", "assistant"]
    assert await message_roles(second) == ["user", "assistant"]
    assert set(await message_ids(second)).isdisjoint(first_ids)

    grandparent = await _strategy_of(thread.conversation_id)
    parent = await _strategy_of(first)
    child = await _strategy_of(second)
    assert grandparent is not None
    assert parent is not None
    assert child is not None
    assert set(step_ids_of(child.strategy_ast)) == set(THREE_STEPS)
    assert push.pushed_strategy_ids == [
        parent.wdk_strategy_id,
        child.wdk_strategy_id,
    ]
    child_steps = set(step_ids_of(child.strategy_ast).values())
    assert child_steps.isdisjoint(step_ids_of(parent.strategy_ast).values())
    assert child_steps.isdisjoint(step_ids_of(grandparent.strategy_ast).values())

    async with db.async_session_factory() as session:
        branch_row = await session.get(Conversation, second)
        assert branch_row is not None
        assert branch_row.parent_conversation_id == first
        assert branch_row.parent_message_id == UUID(first_ids[1])


# F5: fork ids are fresh everywhere; task_id is null; the architecture carries.


async def test_f5_every_id_in_a_branch_is_the_branch_s_own(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    task_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(
            BackgroundTask(
                id=task_id,
                conversation_id=thread.conversation_id,
                user_id=user_id,
                tool_name="run_eda_compute",
                status="complete",
            ),
        )
        await session.flush()
        session.add(
            ConversationEvent(
                conversation_id=thread.conversation_id,
                task_id=task_id,
                turn_id=thread.answer_two,
                chunk={"type": "data-task-progress", "data": {"percent": 50}},
            ),
        )
        await session.commit()

    fork_id = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )

    parent_message_ids = set(await message_ids(thread.conversation_id))
    fork_message_ids = set(await message_ids(fork_id))
    async with db.async_session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(ConversationEvent)
                    .where(ConversationEvent.conversation_id == fork_id)
                    .order_by(ConversationEvent.id),
                )
            )
            .scalars()
            .all()
        )
        source = await session.get(Conversation, thread.conversation_id)
        branch = await session.get(Conversation, fork_id)
    assert rows
    assert source is not None
    assert branch is not None
    turn_ids = {str(row.turn_id) for row in rows if row.turn_id is not None}
    chunk_ids: set[str] = set()
    for row in rows:
        chunk_ids |= message_ids_in(row.chunk)
    assert turn_ids
    assert turn_ids.isdisjoint(parent_message_ids)
    assert turn_ids <= fork_message_ids
    assert chunk_ids.isdisjoint(parent_message_ids)
    assert chunk_ids <= fork_message_ids
    assert [row.task_id for row in rows] == [None] * len(rows)
    assert branch.assistant_id == source.assistant_id
    assert branch.application_id == source.application_id


# F6: forking is repeatable, and it never mutates the parent.


async def test_f6_two_branches_of_one_anchor_are_independent(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    push = install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    first = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_two,
        user_id=user_id,
    )
    second = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_two,
        user_id=user_id,
    )

    assert first != second
    assert set(await message_ids(first)).isdisjoint(await message_ids(second))
    left = await _strategy_of(first)
    right = await _strategy_of(second)
    assert left is not None
    assert right is not None
    assert left.wdk_strategy_id != right.wdk_strategy_id
    assert push.pushed_strategy_ids == [
        left.wdk_strategy_id,
        right.wdk_strategy_id,
    ]
    assert set(step_ids_of(left.strategy_ast).values()).isdisjoint(
        step_ids_of(right.strategy_ast).values(),
    )
    assert await message_roles(first) == await message_roles(second)


async def test_f6_forking_leaves_every_parent_row_unchanged(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    before = (
        await conversation_snapshot(thread.conversation_id),
        await thread_content_snapshot(thread.conversation_id),
    )
    await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_two,
        user_id=user_id,
    )
    await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )

    assert await conversation_snapshot(thread.conversation_id) == before[0]
    assert await thread_content_snapshot(thread.conversation_id) == before[1]


# F7: the EDA binding is the thread's own; a branch never mutates the parent's.


async def test_f7_a_branch_opens_the_anchor_s_study_in_a_document_of_its_own(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The branch shows the study its transcript shows, and authors its own."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    subset = [gametocyte_filter("gametocyte", "ring")]
    eda.document("a1b2c3d4", subset)
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="a1b2c3d4",
        filters=subset,
    )
    await bind_analysis(thread.conversation_id, analysis_id="a1b2c3d4")

    fork_id = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )

    branch = await bound_analysis(fork_id)
    assert branch is not None
    assert branch.analysis_id == "fresh1"
    assert branch.dataset_id == EDA_DATASET
    assert branch.site_id == "plasmodb"
    assert branch.revision == 1
    assert eda.created == [(EDA_DATASET, "gametocyte rows")]
    assert eda.documents["fresh1"] == subset
    # The parent's own document is neither shared nor rewritten.
    assert eda.documents["a1b2c3d4"] == subset
    parent = await bound_analysis(thread.conversation_id)
    assert parent is not None
    assert parent.analysis_id == "a1b2c3d4"
    assert parent.revision == 1


async def test_f7_a_branch_anchored_before_the_bind_opens_no_study(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The bind belongs to turn 4, so a branch at turn 2 never saw a study."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    eda.document("a1b2c3d4")
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="a1b2c3d4",
    )
    await bind_analysis(thread.conversation_id, analysis_id="a1b2c3d4")

    fork_id = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_two,
        user_id=user_id,
    )

    assert await bound_analysis(fork_id) is None
    assert eda.created == []


async def test_f7_a_study_service_refusal_leaves_the_branch_unbound(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A dead binding must not cost the user the branch."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    eda.refuse_create = True
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    eda.document("a1b2c3d4")
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="a1b2c3d4",
    )
    await bind_analysis(thread.conversation_id, analysis_id="a1b2c3d4")

    fork_id = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )

    assert await message_roles(fork_id) == ["user", "assistant", "user", "assistant"]
    assert await bound_analysis(fork_id) is None
    parent = await bound_analysis(thread.conversation_id)
    assert parent is not None
    assert parent.analysis_id == "a1b2c3d4"


# F8: library rows stay the user's; a branch owns its gene set.


async def _seed_gene_set(user_id: UUID) -> str:
    gene_set_id = str(uuid4())[:50]
    async with db.async_session_factory() as session:
        session.add(
            GeneSetRow(
                id=gene_set_id,
                user_id=user_id,
                site_id="plasmodb",
                name="protease work",
                gene_ids=["PF3D7_0100100", "PF3D7_0200200"],
                source="strategy",
                wdk_strategy_id=SOURCE_WDK_STRATEGY_ID,
                step_count=3,
            ),
        )
        await session.commit()
    return gene_set_id


async def _link_gene_set(conversation_id: UUID, *, gene_set_id: str) -> None:
    async with db.async_session_factory() as session:
        row = await session.get(ConversationStrategy, conversation_id)
        assert row is not None
        row.gene_set_id = gene_set_id
        row.gene_set_auto_imported = True
        await session.commit()


async def test_f8_a_branch_owns_its_gene_set(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A branch has a WDK strategy of its own, so it must not point at the
    parent's gene set: the next build resyncs whatever it points at."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    gene_set_id = await _seed_gene_set(user_id)
    await _link_gene_set(thread.conversation_id, gene_set_id=gene_set_id)

    fork_id = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )

    branch = await _strategy_of(fork_id)
    parent = await _strategy_of(thread.conversation_id)
    assert branch is not None
    assert parent is not None
    assert branch.gene_set_id is None
    assert branch.gene_set_auto_imported is False
    assert parent.gene_set_id == gene_set_id
    assert parent.gene_set_auto_imported is True

    async with db.async_session_factory() as session:
        gene_set = await session.get(GeneSetRow, gene_set_id)
        assert gene_set is not None
        assert gene_set.wdk_strategy_id == SOURCE_WDK_STRATEGY_ID
        assert list(gene_set.gene_ids) == ["PF3D7_0100100", "PF3D7_0200200"]


# F9: cross-thread memory is user-scoped, so surgery changes nothing there.


def _memory(name: str, summary: str) -> MemoryValue:
    return MemoryValue(
        kind="knowledge",
        name=name,
        summary=summary,
        tags=[],
        content={"fact": summary},
        created_at=datetime.now(UTC),
    )


def _pipeline_state(conversation_id: UUID, user_id: UUID) -> PipelineState:
    return PipelineState(
        conversation_id=conversation_id,
        user_id=user_id,
        site_id="plasmodb",
        mode="strategy",
        user_prompt="which proteases are expressed in gametocytes",
    )


def _context(user_id: UUID, memory_store: Any) -> Context:
    return Context(
        site_id="plasmodb",
        user_id=user_id,
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=db.async_session_factory,
        cancel_event=asyncio.Event(),
        memory_store=memory_store,
    )


async def test_f9_a_branch_turn_retrieves_the_memories_its_parent_would(
    patch_app_db_engine: None,
    app_memory_store: MemoryStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    conversation_id = await seed_conversation(user_id)
    anchor = await add_user_message(conversation_id)
    await write_strategy(conversation_id, THREE_STEPS)
    await add_assistant_message(conversation_id)
    for value in (
        _memory("protease panel", "the gametocyte proteases of interest"),
        _memory("organism default", "the user works on P. falciparum 3D7"),
    ):
        await app_memory_store.put(user_id=user_id, value=value)

    fork_id = await _fork(
        source_conversation_id=conversation_id,
        from_message_id=anchor,
        user_id=user_id,
    )

    runtime: Runtime[Context] = Runtime(
        context=_context(user_id, app_memory_store.store),
    )
    on_parent = await _lead_turn.retrieve_memories(
        _pipeline_state(conversation_id, user_id),
        runtime,
    )
    on_branch = await _lead_turn.retrieve_memories(
        _pipeline_state(fork_id, user_id),
        runtime,
    )

    assert [stored.key for stored in on_parent]
    assert [stored.key for stored in on_branch] == [stored.key for stored in on_parent]


# F1 to F4 together, on a tree of three threads.


async def test_the_branch_tree_holds_f1_to_f4_together(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Six messages and two edits, branched twice."""
    del patch_app_db_engine, db_cleaner
    push: FakePush = install_fake_push(monkeypatch)
    user_id = await seed_user()
    conversation_id = await seed_conversation(user_id)
    await add_user_message(conversation_id)
    await write_strategy(conversation_id, THREE_STEPS)
    answer_two = await add_assistant_message(conversation_id)
    await add_user_message(conversation_id)
    await write_strategy(conversation_id, FOUR_STEPS)
    answer_four = await add_assistant_message(conversation_id)
    await add_user_message(conversation_id)
    await add_assistant_message(conversation_id)

    branch = await _fork(
        source_conversation_id=conversation_id,
        from_message_id=answer_four,
        user_id=user_id,
    )
    branch_message_ids = await message_ids(branch)
    twig = await _fork(
        source_conversation_id=branch,
        from_message_id=UUID(branch_message_ids[1]),
        user_id=user_id,
    )

    assert await message_roles(conversation_id) == [
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert await message_roles(branch) == ["user", "assistant", "user", "assistant"]
    assert await message_roles(twig) == ["user", "assistant"]

    root = await _strategy_of(conversation_id)
    branch_strategy = await _strategy_of(branch)
    twig_strategy = await _strategy_of(twig)
    assert root is not None
    assert branch_strategy is not None
    assert twig_strategy is not None
    assert set(step_ids_of(branch_strategy.strategy_ast)) == set(FOUR_STEPS)
    assert set(step_ids_of(twig_strategy.strategy_ast)) == set(THREE_STEPS)
    assert (
        len(
            {
                root.wdk_strategy_id,
                branch_strategy.wdk_strategy_id,
                twig_strategy.wdk_strategy_id,
            }
        )
        == 3
    )
    assert push.pushed_strategy_ids == [
        branch_strategy.wdk_strategy_id,
        twig_strategy.wdk_strategy_id,
    ]
    assert str(answer_two) not in branch_message_ids
    assert set(await message_ids(twig)).isdisjoint(branch_message_ids)
