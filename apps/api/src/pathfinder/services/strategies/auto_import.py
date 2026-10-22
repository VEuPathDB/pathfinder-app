"""The gene set a WDK-linked chat's build creates and links.

Once imported (or once the user deletes the set), the chat is marked so a
later build does not recreate it. ``gene_set_refresh`` keeps the set current.
"""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from sqlalchemy import text
from veupathdb.errors import VEuPathDBError

from pathfinder.domain.gene_homes import holds_genes
from pathfinder.domain.strategy.revision import answer_revision, parse_strategy_ast
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
)
from pathfinder.services.gene_sets.homes import site_kind
from pathfinder.services.gene_sets.operations import EmptyGeneSetError, GeneSetService
from pathfinder.services.gene_sets.step_genes import TooManyGenesError
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.services.gene_sets.strategy_genes import RecordsAreNotGenesError
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.strategies.write_lock import strategy_write_lock

logger = get_logger(__name__)


class StrategyLinkWriter(Protocol):
    """The writes auto-import makes on a thread store."""

    async def update_conversation(
        self,
        conversation_id: UUID,
        upd: ConversationUpdate,
        /,
    ) -> None: ...

    async def name_and_link(
        self, conversation_id: UUID, gene_set: GeneSet, /
    ) -> None: ...


@dataclass(frozen=True)
class _ThreadLinks:
    repo: ConversationRepository
    service: GeneSetService

    async def update_conversation(
        self, conversation_id: UUID, upd: ConversationUpdate, /
    ) -> None:
        await self.repo.update_conversation(conversation_id, upd)

    async def name_and_link(self, conversation_id: UUID, gene_set: GeneSet, /) -> None:
        async with strategy_write_lock(
            conversation_id, async_session_factory
        ) as session:
            repo = ConversationRepository(session)
            found = await repo.get_with_strategy(conversation_id)
            named = "" if found is None else found[0].name
            if named and named != gene_set.name:
                await self.service.rename(gene_set, named)
            await repo.update_conversation(
                conversation_id,
                ConversationUpdate(
                    gene_set_id=gene_set.id,
                    gene_set_id_set=True,
                    gene_set_auto_imported=True,
                ),
            )


class GeneSetImporter(Protocol):
    """The gene set surface auto-import calls."""

    async def find_strategy_import(
        self,
        user_id: UUID,
        wdk_strategy_id: int,
        /,
    ) -> GeneSet | None: ...

    async def create_from_strategy(
        self,
        *,
        user_id: UUID,
        name: str,
        site_id: str,
        wdk_strategy_id: int,
        record_type: str | None,
    ) -> GeneSet: ...

    async def save(self, gene_set: GeneSet, /) -> None: ...


def _is_eligible(strategy: ConversationStrategyView) -> bool:
    """Check if a chat is eligible for gene set auto-import.

    Eligible when:
    - Has a WDK strategy ID (is a WDK-linked strategy)
    - Has not been auto-imported before (one-way latch)
    - Does not already have a linked gene set
    """
    return (
        strategy.wdk_strategy_id is not None
        and not strategy.gene_set_auto_imported
        and strategy.gene_set_id is None
    )


async def auto_import_gene_set(
    thread: ConversationWithStrategy,
    *,
    name: str,
    conv_repo: StrategyLinkWriter,
    gene_set_service: GeneSetImporter,
    site_id: str,
    user_id: UUID,
) -> GeneSet | None:
    """Create the thread's gene set under ``name`` and link it to the thread.

    Returns the created set, or None when the thread is not eligible, its
    strategy holds records that are not genes, an earlier import already made
    its set, or its strategy returned no genes or more records than the cap.
    """
    conversation, strategy = thread
    wdk_id = strategy.wdk_strategy_id
    if (
        wdk_id is None
        or not _is_eligible(strategy)
        or (
            strategy.record_type is not None
            and not holds_genes(site_kind(site_id), strategy.record_type)
        )
    ):
        return None
    revision = answer_revision(parse_strategy_ast(strategy.strategy_ast))

    # Only a set an earlier import made is linked; a set the researcher saved
    # on the same strategy stays theirs.
    existing = await gene_set_service.find_strategy_import(user_id, wdk_id)
    if existing:
        await conv_repo.update_conversation(
            conversation.id,
            ConversationUpdate(
                gene_set_id=existing.id,
                gene_set_id_set=True,
                gene_set_auto_imported=True,
            ),
        )
        return None

    try:
        gs = await gene_set_service.create_from_strategy(
            user_id=user_id,
            name=name,
            site_id=site_id,
            wdk_strategy_id=wdk_id,
            record_type=strategy.record_type,
        )
        gs.answer_revision = revision
        await gene_set_service.save(gs)
        await conv_repo.name_and_link(conversation.id, gs)
    except (EmptyGeneSetError, RecordsAreNotGenesError, TooManyGenesError) as exc:
        # Expected, not a failure: leave the latch off so a later write
        # whose root returns genes still gets imported.
        logger.info(
            "Skipped gene set auto-import",
            wdk_strategy_id=wdk_id,
            reason=exc.detail,
        )
        return None
    except (VEuPathDBError, RuntimeError) as exc:
        logger.warning(
            "Failed to auto-import gene set for chat",
            wdk_strategy_id=wdk_id,
            error=str(exc),
        )
        return None
    logger.info(
        "Auto-imported gene set for chat",
        gene_set_id=gs.id,
        wdk_strategy_id=wdk_id,
        gene_count=len(gs.gene_ids),
    )
    return gs


async def import_gene_set_for_conversation(
    *,
    conversation_id: UUID,
    site_id: str,
    user_id: UUID,
    name: str,
) -> GeneSet | None:
    """Create + link a gene set for a single just-built conversation.

    Called inline after an auto-build commits ``wdk_strategy_id``, and by the
    refresh job after a later write, so a fresh session sees it. Idempotent
    (``_is_eligible`` + ``find_strategy_import``), and the imports of one thread
    run one at a time. Returns the created gene set, or ``None`` if
    ineligible/already imported. The set takes the name the thread holds when
    the link is written; ``name`` stands in until the thread has one.
    """
    async with async_session_factory() as session:
        try:
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"),
                {"k": f"gene-set-import:{conversation_id}"},
            )
            repo = ConversationRepository(session)
            found = await repo.get_with_strategy(conversation_id)
            if found is None:
                return None
            conversation, strategy = found
            gene_set_svc = GeneSetService(get_gene_set_store())
            created = await auto_import_gene_set(
                (conversation, strategy),
                name=conversation.name or name,
                conv_repo=_ThreadLinks(repo, gene_set_svc),
                gene_set_service=gene_set_svc,
                site_id=site_id,
                user_id=user_id,
            )
            await session.commit()
        except (VEuPathDBError, RuntimeError) as e:
            await session.rollback()
            logger.warning(
                "Gene set auto-import for conversation failed",
                conversation_id=str(conversation_id),
                error=str(e),
            )
            return None
        return created
