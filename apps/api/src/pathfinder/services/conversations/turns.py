"""The reads and writes one assistant turn makes on the thread it runs on."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import DBSessionFactory, async_session_factory
from veupathdb.domain.strategy import StrategyAst, extract_output_organisms, walk

from pathfinder.domain.strategy.generated_name import (
    name_outdated,
    name_seed,
    named_steps,
)
from pathfinder.domain.strategy.revision import parse_strategy_ast
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.services.strategies.naming import (
    NamedThread,
    name_if_unnamed,
    name_the_thread,
    put_the_name_on_wdk,
)
from pathfinder.services.strategies.organism_params import organism_parameters
from pathfinder.services.strategies.write_lock import strategy_write_lock

LOCK_WAIT_SECONDS = 10
"""The longest a title waits on the thread's strategy lock and its writes."""

TitleGenerator = Callable[[str], Awaitable[str]]
"""Generates a thread title from a seed text. The AI layer supplies it."""


async def load_conversation(conversation_id: UUID) -> Conversation | None:
    """The thread a turn runs on, or None when no such thread exists."""
    async with async_session_factory() as session:
        return await ConversationRepository(session).get_by_id(conversation_id)


async def name_conversation_if_unnamed(conversation_id: UUID, *, title: str) -> bool:
    """Give the thread a generated title, keeping any name it already holds.

    Reports whether the title was written. The strategy carries the name the
    thread holds either way. The lock is waited on for a bounded time and is
    released before the name goes to WDK.
    """
    async with asyncio.timeout(LOCK_WAIT_SECONDS):
        async with strategy_write_lock(
            conversation_id, async_session_factory
        ) as locked:
            title_write = await name_if_unnamed(
                ConversationRepository(locked), conversation_id, title=title
            )
    if title_write.named is not None:
        await put_the_name_on_wdk(title_write.named)
    return title_write.written


async def turn_start_strategy(conversation_id: UUID) -> StrategyAst | None:
    """The strategy the thread holds as the turn opens."""
    async with async_session_factory() as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)
    return parse_strategy_ast(strategy.strategy_ast)


async def _organisms(site_id: str, now: StrategyAst | None) -> set[str]:
    """The organisms the strategy's result is scoped to, as the catalog marks them."""
    if now is None:
        return set()
    searches = [
        node.search_name for node in walk(now.root) if node.infer_kind() != "combine"
    ]
    marks = await organism_parameters(site_id, now.record_type, searches)
    return extract_output_organisms(now.root, marks) or set()


async def _mark(conversation_id: UUID, *, held: list[str], covers: list[str]) -> None:
    """Record the steps a generated name covers, while the thread holds ``held``."""
    async with asyncio.timeout(LOCK_WAIT_SECONDS):
        async with strategy_write_lock(
            conversation_id, async_session_factory
        ) as locked:
            threads = ConversationRepository(locked)
            strategy = await threads.get_strategy(conversation_id)
            if strategy.generated_name_steps != held:
                return
            await threads.update_conversation(
                conversation_id,
                ConversationUpdate(
                    generated_name_steps=covers,
                    generated_name_steps_set=True,
                    touch_updated_at=False,
                ),
            )


async def _rename(
    conversation_id: UUID, *, held: list[str], title: str
) -> NamedThread | None:
    """Write ``title`` as a generated name, while the thread holds ``held``."""
    async with asyncio.timeout(LOCK_WAIT_SECONDS):
        async with strategy_write_lock(
            conversation_id, async_session_factory
        ) as locked:
            threads = ConversationRepository(locked)
            strategy = await threads.get_strategy(conversation_id)
            if strategy.generated_name_steps != held:
                return None
            return await name_the_thread(
                threads,
                conversation_id,
                title,
                generated_over=named_steps(parse_strategy_ast(strategy.strategy_ast)),
            )


async def _seed_of_a_new_name(
    conversation: Conversation,
    strategy: ConversationStrategyView,
    held: list[str],
    start: StrategyAst | None,
) -> str:
    """The seed of a new name, or empty when the name stands.

    A name written before any step takes the steps built after it.
    """
    now = parse_strategy_ast(strategy.strategy_ast)
    if not held:
        if covers := named_steps(now):
            await _mark(conversation.id, held=held, covers=covers)
        return ""
    if not name_outdated(conversation.name, held, start=start, now=now):
        return ""
    seed = name_seed(now, await _organisms(conversation.site_id, now))
    if not seed:
        await _mark(conversation.id, held=held, covers=[])
    return seed


async def rename_if_edits_outdated_it(
    conversation_id: UUID,
    *,
    start: StrategyAst | None,
    title_for: TitleGenerator,
) -> str | None:
    """Generate the thread's name anew when an edit outdated it.

    Only a generated name changes, and its seed is the steps left, never a
    message. Returns the stored name, or None when the name stands.
    """
    async with async_session_factory() as session:
        found = await ConversationRepository(session).get_with_strategy(conversation_id)
    if found is None:
        return None
    conversation, strategy = found
    held = strategy.generated_name_steps
    if held is None:
        return None
    seed = await _seed_of_a_new_name(conversation, strategy, held, start)
    title = await title_for(seed) if seed else ""
    named = await _rename(conversation_id, held=held, title=title) if title else None
    if named is None:
        return None
    await put_the_name_on_wdk(named)
    return named.name


async def turn_start_revision_id(conversation_id: UUID) -> int | None:
    """The strategy snapshot the thread holds as the turn opens."""
    async with async_session_factory() as session:
        latest = await StrategyRevisionRepository(session).latest(conversation_id)
    return None if latest is None else latest.id


async def name_turn_strategy_revision(
    session_factory: DBSessionFactory,
    *,
    conversation_id: UUID,
    message_id: UUID,
) -> None:
    """Record which message the strategy the turn left behind belongs to."""
    async with session_factory() as session:
        await StrategyRevisionRepository(session).name_latest(
            conversation_id,
            message_id=message_id,
        )
        await session.commit()
