"""The revert case matrix: R1 to R7 of the thread-surgery invariants.

Each test names the invariant it holds. The invariants are written down in
``docs/knowledge/conventions/thread-surgery-invariants.md``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID, uuid4

import pytest
from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.persistence.models import (
    BackgroundTask,
    ConversationEvent,
    TaskProgressRow,
)
from assistant_core.platform import db
from sqlalchemy import func, select, text

from pathfinder.persistence.models import ConversationStrategy, StrategyRevision
from pathfinder.platform.config import get_settings
from pathfinder.services.conversations.fork import fork_conversation
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.tests.integration.persistence._fake_eda import install_fake_eda
from pathfinder.tests.integration.persistence._thread_surgery import (
    EDA_DATASET,
    FOUR_STEPS,
    SOURCE_WDK_STRATEGY_ID,
    THREE_STEPS,
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


async def _revert(
    *,
    conversation_id: UUID,
    target_message_id: UUID,
    user_id: UUID,
) -> None:
    async with db.async_session_factory() as session:
        await revert_conversation_to_message(
            session,
            conversation_id=conversation_id,
            target_message_id=target_message_id,
            user_id=user_id,
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


async def _turn_ids_in_log(conversation_id: UUID) -> set[str]:
    async with db.async_session_factory() as session:
        rows = (
            await session.execute(
                select(ConversationEvent.turn_id).where(
                    ConversationEvent.conversation_id == conversation_id,
                ),
            )
        ).scalars()
    return {str(turn_id) for turn_id in rows if turn_id is not None}


async def _revision_step_counts(conversation_id: UUID) -> list[int]:
    async with db.async_session_factory() as session:
        return list(
            (
                await session.execute(
                    select(StrategyRevision.step_count)
                    .where(StrategyRevision.conversation_id == conversation_id)
                    .order_by(StrategyRevision.id),
                )
            ).scalars(),
        )


# R1 and R2: the cut removes the turns after the target, and the strategy
# returns to the state in force at it.


async def test_r1_a_revert_deletes_exactly_the_turns_after_the_target(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    push = install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    surviving = set((await message_ids(thread.conversation_id))[:2])

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )

    assert await message_roles(thread.conversation_id) == ["user", "assistant"]
    assert set(await message_ids(thread.conversation_id)) == surviving
    assert await _turn_ids_in_log(thread.conversation_id) == surviving
    assert await _revision_step_counts(thread.conversation_id) == [3, 3]
    strategy = await _strategy_of(thread.conversation_id)
    assert strategy is not None
    assert set(step_ids_of(strategy.strategy_ast)) == set(THREE_STEPS)
    assert strategy.wdk_strategy_id == push.pushed_strategy_ids[0]
    assert strategy.wdk_strategy_id != SOURCE_WDK_STRATEGY_ID


async def _strategy_of(conversation_id: UUID) -> ConversationStrategy | None:
    async with db.async_session_factory() as session:
        return await session.get(ConversationStrategy, conversation_id)


# R4: reverting to the same message again is a no-op with the same end state.


async def test_r4_reverting_twice_to_one_message_ends_where_once_did(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )
    after_once = await thread_content_snapshot(thread.conversation_id)

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )

    assert await thread_content_snapshot(thread.conversation_id) == after_once


# R5: a revert inside a branch works against that branch's own ids.


async def test_r5_a_revert_inside_a_branch_of_a_branch_uses_that_branch_s_ids(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The branch's own history is the only history the cut may read."""
    del patch_app_db_engine, db_cleaner
    push = install_fake_push(monkeypatch)
    user_id = await seed_user()
    conversation_id = await seed_conversation(user_id)
    await add_user_message(conversation_id)
    await write_strategy(conversation_id, THREE_STEPS)
    await add_assistant_message(conversation_id)
    await add_user_message(conversation_id)
    await write_strategy(conversation_id, FOUR_STEPS)
    await add_assistant_message(conversation_id)
    await add_user_message(conversation_id)
    answer_six = await add_assistant_message(conversation_id)

    branch = await _fork(
        source_conversation_id=conversation_id,
        from_message_id=answer_six,
        user_id=user_id,
    )
    branch_ids = await message_ids(branch)
    twig = await _fork(
        source_conversation_id=branch,
        from_message_id=UUID(branch_ids[3]),
        user_id=user_id,
    )
    twig_ids = await message_ids(twig)
    parent_before = await thread_content_snapshot(conversation_id)
    branch_before = await thread_content_snapshot(branch)
    twig_before = await _strategy_of(twig)
    assert twig_before is not None
    assert twig_before.wdk_strategy_id == push.pushed_strategy_ids[1]
    assert set(step_ids_of(twig_before.strategy_ast)) == set(FOUR_STEPS)

    await _revert(
        conversation_id=twig,
        target_message_id=UUID(twig_ids[2]),
        user_id=user_id,
    )

    assert await message_roles(twig) == ["user", "assistant"]
    assert await message_ids(twig) == twig_ids[:2]
    assert await _turn_ids_in_log(twig) == set(twig_ids[:2])
    twig_strategy = await _strategy_of(twig)
    assert twig_strategy is not None
    assert twig_strategy.step_count == 3
    # The restored snapshot is pushed, so the twig holds a live strategy of its
    # own rather than the plan its copied history recorded.
    assert set(step_ids_of(twig_strategy.strategy_ast)) == set(THREE_STEPS)
    assert twig_strategy.wdk_strategy_id == push.pushed_strategy_ids[2]
    assert twig_strategy.wdk_strategy_id != twig_before.wdk_strategy_id
    assert set(step_ids_of(twig_strategy.strategy_ast).values()).isdisjoint(
        step_ids_of(twig_before.strategy_ast).values(),
    )
    assert await thread_content_snapshot(conversation_id) == parent_before
    assert await thread_content_snapshot(branch) == branch_before


async def test_r5_a_revert_inside_a_branch_keeps_the_surviving_turns_chunks(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The log is the source of truth for parts, so a cut that takes the
    surviving turns' chunks leaves the branch rendering empty messages."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    branch = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )
    branch_ids = await message_ids(branch)

    await _revert(
        conversation_id=branch,
        target_message_id=UUID(branch_ids[2]),
        user_id=user_id,
    )

    assert await message_ids(branch) == branch_ids[:2]
    assert await _turn_ids_in_log(branch) == set(branch_ids[:2])


async def test_r5_a_revert_inside_a_branch_keeps_the_notes_of_surviving_turns(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    conversation_id = await seed_conversation(user_id)
    await add_user_message(conversation_id)
    await write_strategy(conversation_id, THREE_STEPS)
    await add_note(conversation_id, "proteases shortlisted")
    await add_assistant_message(conversation_id)
    await add_user_message(conversation_id)
    await write_strategy(conversation_id, FOUR_STEPS)
    answer_four = await add_assistant_message(conversation_id)
    branch = await _fork(
        source_conversation_id=conversation_id,
        from_message_id=answer_four,
        user_id=user_id,
    )
    branch_ids = await message_ids(branch)

    await _revert(
        conversation_id=branch,
        target_message_id=UUID(branch_ids[2]),
        user_id=user_id,
    )

    assert await note_titles(branch) == ["proteases shortlisted"]


# R6: a revert leaves the thread's siblings untouched.


async def test_r6_reverting_one_branch_leaves_its_sibling_and_parent_alone(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    left = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )
    right = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )
    left_ids = await message_ids(left)
    parent_row_before = await conversation_snapshot(thread.conversation_id)
    parent_before = await thread_content_snapshot(thread.conversation_id)
    right_row_before = await conversation_snapshot(right)
    right_before = await thread_content_snapshot(right)

    await _revert(
        conversation_id=left,
        target_message_id=UUID(left_ids[2]),
        user_id=user_id,
    )

    assert await message_roles(left) == ["user", "assistant"]
    assert await conversation_snapshot(thread.conversation_id) == parent_row_before
    assert await thread_content_snapshot(thread.conversation_id) == parent_before
    assert await conversation_snapshot(right) == right_row_before
    assert await thread_content_snapshot(right) == right_before


async def test_r6_reverting_the_parent_leaves_each_branch_s_content_alone(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The branch point's message row goes, so the branch's back-reference
    nulls; nothing the branch holds moves."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    left = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_four,
        user_id=user_id,
    )
    right = await _fork(
        source_conversation_id=thread.conversation_id,
        from_message_id=thread.answer_two,
        user_id=user_id,
    )
    left_before = await thread_content_snapshot(left)
    right_row_before = await conversation_snapshot(right)
    right_before = await thread_content_snapshot(right)

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )

    assert await thread_content_snapshot(left) == left_before
    assert await thread_content_snapshot(right) == right_before
    assert await conversation_snapshot(right) == right_row_before
    assert await conversation_snapshot(left) != left_before
    assert (await conversation_snapshot(left))["parent_message_id"] == "None"


# R7: task rows the deleted turns created do not come back; the EDA binding
# is not cut with them.


async def _task_and_progress_counts(conversation_id: UUID) -> tuple[int, int]:
    async with db.async_session_factory() as session:
        tasks = (
            await session.scalar(
                select(func.count())
                .select_from(BackgroundTask)
                .where(BackgroundTask.conversation_id == conversation_id),
            )
        ) or 0
        progress = (
            await session.scalar(
                select(func.count())
                .select_from(TaskProgressRow)
                .join(BackgroundTask, TaskProgressRow.task_id == BackgroundTask.id)
                .where(BackgroundTask.conversation_id == conversation_id),
            )
        ) or 0
    return tasks, progress


async def _seed_task(conversation_id: UUID, user_id: UUID) -> None:
    task_id = uuid4()
    async with db.async_session_factory() as session:
        session.add(
            BackgroundTask(
                id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                tool_name="run_eda_compute",
                status="complete",
            ),
        )
        await session.flush()
        session.add(
            TaskProgressRow(task_id=task_id, percent=50.0, message="volcano ready"),
        )
        await session.commit()


async def test_r7_a_revert_past_the_bind_removes_the_tasks_and_the_binding(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turn 3 opened the study, so the surviving log records none."""
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
    await _seed_task(thread.conversation_id, user_id)
    assert await _task_and_progress_counts(thread.conversation_id) == (1, 1)

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )

    assert await _task_and_progress_counts(thread.conversation_id) == (0, 0)
    assert await bound_analysis(thread.conversation_id) is None
    assert eda.created == []


async def test_r7_a_revert_puts_the_recorded_filters_back_on_the_open_analysis(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Turn 4 refiltered the same document, so the revert puts turn 2's back."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    at_turn_two = [gametocyte_filter("gametocyte")]
    at_turn_four = [gametocyte_filter("gametocyte", "ring")]
    eda.document("a1b2c3d4", at_turn_four)
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_two,
        analysis_id="a1b2c3d4",
        filters=at_turn_two,
    )
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="a1b2c3d4",
        filters=at_turn_four,
    )
    await bind_analysis(thread.conversation_id, analysis_id="a1b2c3d4", revision=2)

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )

    binding = await bound_analysis(thread.conversation_id)
    assert binding is not None
    assert binding.analysis_id == "a1b2c3d4"
    assert binding.revision == 3
    assert eda.documents["a1b2c3d4"] == at_turn_two
    assert eda.patched == [("a1b2c3d4", at_turn_two)]
    assert eda.created == []


async def test_r7_a_revert_rebinds_the_analysis_the_deleted_turns_replaced(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replacing a binding leaves the replaced document in place, so it is reused."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    first_subset = [gametocyte_filter("gametocyte")]
    eda.document("a1b2c3d4", [])
    eda.document("z9y8x7w6", [gametocyte_filter("ring")])
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_two,
        analysis_id="a1b2c3d4",
        filters=first_subset,
    )
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="z9y8x7w6",
        filters=[gametocyte_filter("ring")],
    )
    await bind_analysis(thread.conversation_id, analysis_id="z9y8x7w6")

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )

    binding = await bound_analysis(thread.conversation_id)
    assert binding is not None
    assert binding.analysis_id == "a1b2c3d4"
    assert binding.dataset_id == EDA_DATASET
    assert binding.revision == 1
    assert eda.documents["a1b2c3d4"] == first_subset
    assert eda.created == []


async def test_r7_a_revert_recreates_the_recorded_document_when_it_is_gone(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recorded analysis the service no longer serves is opened anew."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    first_subset = [gametocyte_filter("gametocyte")]
    eda.document("z9y8x7w6", [])
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_two,
        analysis_id="a1b2c3d4",
        filters=first_subset,
    )
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="z9y8x7w6",
    )
    await bind_analysis(thread.conversation_id, analysis_id="z9y8x7w6")

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )

    binding = await bound_analysis(thread.conversation_id)
    assert binding is not None
    assert binding.analysis_id == "fresh1"
    assert binding.revision == 1
    assert eda.created == [(EDA_DATASET, "gametocyte rows")]
    assert eda.documents["fresh1"] == first_subset


async def test_r7_a_binding_the_log_never_recorded_survives_the_revert(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A study opened from the tab alone emits no part, so no cut can own it."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    eda.document("a1b2c3d4")
    await bind_analysis(thread.conversation_id, analysis_id="a1b2c3d4", revision=2)

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )

    binding = await bound_analysis(thread.conversation_id)
    assert binding is not None
    assert binding.analysis_id == "a1b2c3d4"
    assert binding.revision == 2
    assert eda.patched == []


async def test_r7_a_study_service_refusal_leaves_the_binding_where_it_was(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The revert must not fail over a document nobody can reach."""
    del patch_app_db_engine, db_cleaner
    install_fake_push(monkeypatch)
    eda = install_fake_eda(monkeypatch)
    eda.refuse_create = True
    user_id = await seed_user()
    thread = await four_turn_thread(user_id)
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_two,
        analysis_id="a1b2c3d4",
        filters=[gametocyte_filter("gametocyte")],
    )
    await add_analysis_state(
        thread.conversation_id,
        turn_id=thread.answer_four,
        analysis_id="z9y8x7w6",
    )
    await bind_analysis(thread.conversation_id, analysis_id="z9y8x7w6")

    await _revert(
        conversation_id=thread.conversation_id,
        target_message_id=thread.user_three,
        user_id=user_id,
    )

    assert await message_roles(thread.conversation_id) == ["user", "assistant"]
    binding = await bound_analysis(thread.conversation_id)
    assert binding is not None
    assert binding.analysis_id == "z9y8x7w6"
    assert binding.revision == 1
