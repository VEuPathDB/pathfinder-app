"""The one name a thread and its strategy share.

The conversation holds the name. The stored strategy, the WDK strategy and the
gene set auto-import made for the thread carry copies of it.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.persistence.repositories.conversation import (
    DEFAULT_CONVERSATION_NAME,
)
from assistant_core.platform.db import DBSessionFactory
from assistant_core.platform.logging import get_logger
from veupathdb.wdk import get_strategy_api

from pathfinder.domain.strategy.revision import parse_strategy_ast
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
)
from pathfinder.platform.errors import NotFoundError
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.write_lock import (
    strategy_write_lock,
    strategy_write_scope,
)

logger = get_logger(__name__)

WDK_RENAME_SECONDS = 10
"""The longest a rename waits on WDK."""

PROVISIONAL_NAME_LENGTH = 60
"""The longest a request stands in for the thread's title, in code points."""

_SPACES = re.compile(
    "[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+"
)
"""The characters that separate words in a request. The web states the same set."""

__all__ = [
    "WDK_RENAME_SECONDS",
    "NamedThread",
    "ThreadNames",
    "TitleWrite",
    "name_for_the_push",
    "name_if_unnamed",
    "name_the_thread",
    "name_the_thread_as_the_graph",
    "placeholder_strategy_name",
    "provisional_strategy_name",
    "put_the_name_on_wdk",
    "rename_strategy_everywhere",
]


class ThreadNames(Protocol):
    """The thread store reads and writes a rename makes."""

    async def get_with_strategy(
        self, conversation_id: UUID, /
    ) -> ConversationWithStrategy | None: ...

    async def update_conversation(
        self, conversation_id: UUID, upd: ConversationUpdate, /
    ) -> None: ...


@dataclass(frozen=True)
class NamedThread:
    """The name the thread stored, and the WDK strategy that carries a copy."""

    name: str
    site_id: str
    wdk_strategy_id: int | None


def placeholder_strategy_name(wdk_strategy_id: int) -> str:
    """The name a WDK strategy that states no name of its own is listed under."""
    return f"WDK Strategy {wdk_strategy_id}"


def provisional_strategy_name(prompt: str) -> str:
    """The request cut on a word at 60 code points, or the placeholder for none.

    The web names an untitled thread in its sidebar by the same rule.
    """
    text = _SPACES.sub(" ", prompt).strip(" ")
    if not text:
        return DEFAULT_CONVERSATION_NAME
    if len(text) <= PROVISIONAL_NAME_LENGTH:
        return text
    head = text[: PROVISIONAL_NAME_LENGTH + 1]
    boundary = head.rfind(" ")
    cut = head[:boundary] if boundary > 0 else text[:PROVISIONAL_NAME_LENGTH]
    return f"{cut}..."


def name_for_the_push(graph: StrategyGraph, user_prompt: str) -> str:
    """The name a push sends. A graph with no name yet takes the request's.

    The request's name is generated, so the thread's first title replaces it.
    """
    if graph.name in {"", DEFAULT_CONVERSATION_NAME}:
        graph.name = provisional_strategy_name(user_prompt)
    return graph.name


async def name_the_thread(
    threads: ThreadNames, conversation_id: UUID, name: str
) -> NamedThread | None:
    """Write the name on the thread, its stored strategy and its imported set.

    The store can adjust the name to keep it unique, so the copies take the
    name it stored. The caller holds the thread's strategy lock.
    """
    found = await threads.get_with_strategy(conversation_id)
    if found is None:
        return None
    conversation, strategy = found
    previous = conversation.name
    written = ConversationUpdate(name=name)
    await threads.update_conversation(conversation_id, written)
    stored = written.name or name
    ast = parse_strategy_ast(strategy.strategy_ast)
    if ast is not None and ast.name != stored:
        await threads.update_conversation(
            conversation_id,
            ConversationUpdate(
                strategy_ast=ast.model_copy(update={"name": stored}),
                touch_updated_at=False,
            ),
        )
    await _rename_the_imported_set(conversation, strategy, previous, stored)
    return NamedThread(
        name=stored,
        site_id=conversation.site_id,
        wdk_strategy_id=strategy.wdk_strategy_id,
    )


async def _rename_the_imported_set(
    conversation: Conversation,
    strategy: ConversationStrategyView,
    previous: str,
    name: str,
) -> None:
    """The set auto-import made keeps the thread's name until someone renames it.

    A set imported before the thread had a name holds a provisional name.
    """
    if strategy.gene_set_id is None or not strategy.gene_set_auto_imported:
        return
    service = GeneSetService(get_gene_set_store())
    try:
        gene_set = await service.get_for_user(
            conversation.user_id, strategy.gene_set_id
        )
    except NotFoundError:
        return
    provisional = {previous}
    if strategy.wdk_strategy_id is not None:
        provisional.add(placeholder_strategy_name(strategy.wdk_strategy_id))
    if previous and gene_set.name not in provisional:
        return
    if gene_set.name != name:
        await service.rename(gene_set, name)


async def name_the_thread_as_the_graph(
    deps: StrategyMutationContext, graph: StrategyGraph
) -> None:
    """A write that renamed the graph renames the thread it belongs to.

    The graph takes the name the thread stored. The push sends the name to WDK.
    """
    scope = strategy_write_scope(deps)
    if scope is None or deps.conversation_id is None:
        return
    async with scope as session:
        named = await name_the_thread(
            ConversationRepository(session), deps.conversation_id, graph.name
        )
    if named is not None:
        graph.name = named.name


async def put_the_name_on_wdk(named: NamedThread) -> None:
    """Send the thread's name to the WDK strategy it holds; never raises.

    The call is bounded. A name WDK did not take is logged: the read before
    the next push finds the name WDK holds, and the push sends the thread's.
    """
    if named.wdk_strategy_id is None:
        return
    try:
        async with asyncio.timeout(WDK_RENAME_SECONDS):
            await get_strategy_api(named.site_id).update_strategy(
                named.wdk_strategy_id, name=named.name
            )
    except Exception:
        logger.exception(
            "WDK did not take the strategy's name",
            wdk_strategy_id=named.wdk_strategy_id,
        )


async def rename_strategy_everywhere(
    conversation_id: UUID, name: str, *, session_factory: DBSessionFactory
) -> str | None:
    """Name the thread and its copies, then WDK; returns the stored name.

    The thread's lock covers the local writes only, so WDK never holds it.
    """
    async with strategy_write_lock(conversation_id, session_factory) as locked:
        named = await name_the_thread(
            ConversationRepository(locked), conversation_id, name
        )
    if named is None:
        return None
    await put_the_name_on_wdk(named)
    return named.name


@dataclass(frozen=True)
class TitleWrite:
    """Whether the title was written, and the name WDK is to carry."""

    written: bool
    named: NamedThread | None = None


async def name_if_unnamed(
    threads: ThreadNames, conversation_id: UUID, *, title: str
) -> TitleWrite:
    """Give an unnamed thread ``title`` on the thread and its local copies.

    A named thread whose stored strategy carries another name takes the
    thread's name back onto its strategy. The caller sends the name to WDK.
    """
    found = await threads.get_with_strategy(conversation_id)
    if found is None:
        return TitleWrite(written=False)
    conversation, strategy = found
    if not conversation.name:
        named = await name_the_thread(threads, conversation_id, title)
        return TitleWrite(written=True, named=named)
    ast = parse_strategy_ast(strategy.strategy_ast)
    if ast is None or ast.name == conversation.name:
        return TitleWrite(written=False)
    named = await name_the_thread(threads, conversation_id, conversation.name)
    return TitleWrite(written=False, named=named)
