"""The gene set a WDK-linked chat's build creates and links.

Once imported (or once the user deletes the set), the chat is marked so a
later build does not recreate it. ``gene_set_refresh`` keeps the set current.
"""

from typing import Protocol
from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp.wdk import GeneSetWdkContext

from pathfinder.domain.strategy.revision import answer_revision, parse_strategy_ast
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
)
from pathfinder.services.gene_sets.operations import EmptyGeneSetError, GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.services.gene_sets.types import GeneSet, GeneSetSource

logger = get_logger(__name__)


class StrategyLinkWriter(Protocol):
    """The one write auto-import makes on a thread store."""

    async def update_conversation(
        self,
        conversation_id: UUID,
        upd: ConversationUpdate,
        /,
    ) -> None: ...


class GeneSetImporter(Protocol):
    """The gene set surface auto-import calls."""

    async def find_strategy_import(
        self,
        user_id: UUID,
        wdk_strategy_id: int,
        /,
    ) -> GeneSet | None: ...

    async def create(
        self,
        *,
        user_id: UUID,
        name: str,
        site_id: str,
        gene_ids: list[str],
        source: GeneSetSource,
        wdk: GeneSetWdkContext | None = None,
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

    Returns the created set, or None when the thread is not eligible, an
    earlier import already made its set, or its strategy returned no genes.
    """
    conversation, strategy = thread
    wdk_id = strategy.wdk_strategy_id
    if wdk_id is None or not _is_eligible(strategy):
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
        gs = await gene_set_service.create(
            user_id=user_id,
            name=name,
            site_id=site_id,
            gene_ids=[],
            source="strategy",
            wdk=GeneSetWdkContext(
                wdk_strategy_id=wdk_id,
                record_type=strategy.record_type,
            ),
        )
        gs.answer_revision = revision
        await gene_set_service.save(gs)
        await conv_repo.update_conversation(
            conversation.id,
            ConversationUpdate(
                gene_set_id=gs.id,
                gene_set_id_set=True,
                gene_set_auto_imported=True,
            ),
        )
    except EmptyGeneSetError:
        # Expected, not a failure: leave the latch off so a later build
        # that actually returns genes still gets imported.
        logger.info(
            "Skipped gene set auto-import: strategy returned 0 genes",
            wdk_strategy_id=wdk_id,
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

    Called inline after an auto-build commits ``wdk_strategy_id``, so a fresh
    session sees it. Idempotent (``_is_eligible`` + ``find_strategy_import``).
    Returns the created gene set, or ``None`` if ineligible/already imported.
    A thread with a name gives the set that name; ``name`` stands in until the
    thread has one.
    """
    async with async_session_factory() as session:
        try:
            repo = ConversationRepository(session)
            found = await repo.get_with_strategy(conversation_id)
            if found is None:
                return None
            conversation, strategy = found
            gene_set_svc = GeneSetService(get_gene_set_store())
            created = await auto_import_gene_set(
                (conversation, strategy),
                name=conversation.name or name,
                conv_repo=repo,
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
