"""The threads the mint release is measured on, and the writers that move them."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from assistant_core.persistence.models import Conversation, Message
from assistant_core.platform.types import JSONObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStepTree, WDKStrategyDetails

from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.persistence.models import GeneSetRow, StrategyRevisionView, User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.persistence.repositories.strategy_revision import (
    StrategyRevisionRepository,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.conversations.revert import revert_conversation_to_message
from pathfinder.services.conversations.update_input import (
    ConversationUpdateInput,
    strategy_write_of,
)
from pathfinder.services.strategies.abandoned_mint import delete_released_mint
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.insert_saved import _record_consumer
from pathfinder.services.strategies.materialize import MaterializedStrategy
from pathfinder.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from pathfinder.services.strategies.revision_ops import discard_turn_strategy_writes
from pathfinder.services.strategies.sync import SyncResult
from pathfinder.services.strategies.sync_state import WDKSyncState

SITE = "plasmodb"
BEFORE = 900
MINTED = 901
ADOPTED = 42
MATERIALIZED = 950
RELEASE_LOGGER = "pathfinder.services.strategies.abandoned_mint"


@dataclass
class FakeStrategyApi:
    """Answers the saved mark and records the deletes the release asks for."""

    refuse: bool = False
    saved_on_site: bool = False
    read_refused: bool = False
    read: list[int] = field(default_factory=list)
    attempted: list[int] = field(default_factory=list)
    deleted: list[int] = field(default_factory=list)

    async def get_strategy(self, strategy_id: int) -> WDKStrategyDetails:
        self.read.append(strategy_id)
        if self.read_refused:
            msg = f"GET /users/1/strategies/{strategy_id}: the site is unavailable"
            raise WDKError(msg, status=503)
        return WDKStrategyDetails(
            strategy_id=strategy_id,
            name="c",
            root_step_id=1,
            is_saved=self.saved_on_site,
            step_tree=WDKStepTree(step_id=1),
        )

    async def delete_strategy(self, strategy_id: int) -> None:
        self.attempted.append(strategy_id)
        if self.refuse:
            msg = "DELETE /users/1/strategies/901: the site is unavailable"
            raise WDKError(msg, status=503)
        self.deleted.append(strategy_id)


@dataclass
class FakePush:
    """Answers a revert's push with a strategy of its own."""

    pushed: list[int] = field(default_factory=list)

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
        strategy_id = MATERIALIZED + len(self.pushed)
        self.pushed.append(strategy_id)
        return MaterializedStrategy(
            strategy_ast=strategy_ast,
            record_type="transcript",
            step_count=1,
            wdk_strategy_id=strategy_id,
            created_wdk_strategy=True,
        )


def _leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_a",
        search_name="GenesByTaxon",
        parameters={"organism": MultiPickValue(values=["Pf3D7"])},
    )


async def seed_thread(db_session: AsyncSession, user: User) -> UUID:
    conv_id = uuid4()
    db_session.add(
        Conversation(
            assistant_id=PATHFINDER_ASSISTANT_ID,
            id=conv_id,
            user_id=user.id,
            site_id=SITE,
            name="c",
        )
    )
    await db_session.commit()
    return conv_id


async def add_message(
    session_maker: async_sessionmaker[AsyncSession],
    conv_id: UUID,
    role: str,
) -> UUID:
    message_id = uuid4()
    async with session_maker() as session:
        session.add(Message(id=message_id, conversation_id=conv_id, role=role))
        await session.commit()
    return message_id


async def persist(
    conv_id: UUID,
    session_maker: async_sessionmaker[AsyncSession],
    wdk_strategy_id: int,
    *,
    created: bool,
) -> None:
    """Write the strategy the way a finished build writes it."""
    strategy_session = StrategySession(site_id=SITE)
    graph = StrategyGraph(graph_id=str(conv_id), name="c", site_id=SITE)
    graph.record_type = "transcript"
    graph.steps.update(flatten_tree(_leaf()))
    graph.recompute_roots()
    strategy_session.graph = graph
    strategy_session.sync_state = WDKSyncState(
        wdk_step_ids={"step_a": 100 + wdk_strategy_id},
        wdk_strategy_id=wdk_strategy_id,
    )
    await persist_strategy_ast_to_conversation(
        deps=StrategyMutationContext(
            site_id=SITE,
            strategy_session=strategy_session,
            conversation_id=conv_id,
            db_session_factory=session_maker,
        ),
        graph=graph,
        sync_result=SyncResult(
            wdk_strategy_id=wdk_strategy_id,
            wdk_url="http://example.invalid",
            root_step_id=100,
            counts={},
            root_count=None,
            zero_step_ids=[],
            step_count=1,
            created_wdk_strategy=created,
        ),
    )


async def latest_revision(
    session_maker: async_sessionmaker[AsyncSession], conv_id: UUID
) -> StrategyRevisionView:
    async with session_maker() as session:
        latest = await StrategyRevisionRepository(session).latest(conv_id)
    assert latest is not None
    return latest


async def stored(
    session_maker: async_sessionmaker[AsyncSession], conv_id: UUID
) -> tuple[int | None, bool]:
    """The thread's WDK strategy id and the record of who made it."""
    async with session_maker() as session:
        row = await ConversationRepository(session).get_strategy(conv_id)
    return row.wdk_strategy_id, row.wdk_strategy_created_here


async def discard(
    session_maker: async_sessionmaker[AsyncSession],
    conv_id: UUID,
    *,
    pre_turn_revision_id: int | None,
) -> None:
    async with session_maker() as session:
        discarded = await discard_turn_strategy_writes(
            session,
            conversation_id=conv_id,
            pre_turn_revision_id=pre_turn_revision_id,
        )
        await session.commit()
    await delete_released_mint(discarded.release)


async def revert(
    session_maker: async_sessionmaker[AsyncSession],
    conv_id: UUID,
    *,
    target: UUID,
    user: User,
) -> None:
    async with session_maker() as session:
        release = await revert_conversation_to_message(
            session,
            conversation_id=conv_id,
            target_message_id=target,
            user_id=user.id,
        )
        await session.commit()
    await delete_released_mint(release)


async def add_gene_set(
    session_maker: async_sessionmaker[AsyncSession],
    user: User,
    *,
    wdk_strategy_id: int,
) -> None:
    """A gene set taken from the strategy during the same turn."""
    async with session_maker() as session:
        session.add(
            GeneSetRow(
                id=f"gs-{wdk_strategy_id}",
                user_id=user.id,
                site_id=SITE,
                name="kinases",
                gene_ids=["PF3D7_0100100"],
                source="strategy",
                wdk_strategy_id=wdk_strategy_id,
            ),
        )
        await session.commit()


async def mark_saved(
    session_maker: async_sessionmaker[AsyncSession],
    conv_id: UUID,
) -> None:
    """Mark the thread saved through the write one PATCH makes."""
    async with session_maker() as session:
        repo = ConversationRepository(session)
        await repo.update_conversation(
            conv_id,
            strategy_write_of(
                ConversationUpdateInput(
                    name=None,
                    strategy_ast=None,
                    wdk_strategy_id=None,
                    wdk_strategy_id_set=False,
                    is_saved=True,
                    is_saved_set=True,
                ),
                held=await repo.get_strategy(conv_id),
                plan=None,
            ),
        )
        await session.commit()


async def record_import(
    session_maker: async_sessionmaker[AsyncSession],
    conv_id: UUID,
    *,
    wdk_strategy_id: int,
) -> None:
    """Record the thread as a consumer of a saved strategy."""
    await _record_consumer(
        deps=StrategyMutationContext(
            site_id=SITE,
            strategy_session=StrategySession(site_id=SITE),
            conversation_id=conv_id,
            db_session_factory=session_maker,
        ),
        wdk_strategy_id=wdk_strategy_id,
    )


async def imported(
    session_maker: async_sessionmaker[AsyncSession],
    conv_id: UUID,
) -> list[int]:
    """The saved strategies the thread names as inputs."""
    async with session_maker() as session:
        row = await ConversationRepository(session).get_strategy(conv_id)
    return list(row.imported_saved_strategy_ids)


async def saved_mark(
    session_maker: async_sessionmaker[AsyncSession],
    conv_id: UUID,
) -> bool:
    """The saved mark the thread's strategy row carries."""
    async with session_maker() as session:
        row = await ConversationRepository(session).get_strategy(conv_id)
    return row.is_saved
