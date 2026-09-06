"""Auto-import gene sets for WDK-linked chats.

When strategies are synced from WDK, eligible chats automatically get a gene
set created and linked. Once imported (or once the user deletes the
auto-imported gene set), the chat is marked so re-syncs don't recreate it.
"""

from uuid import UUID

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp.wdk.gene_set_steps import GeneSetWdkContext

from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
)
from pathfinder.platform.errors import AppError, InternalError
from pathfinder.services.gene_sets.operations import EmptyGeneSetError, GeneSetService
from pathfinder.services.gene_sets.store import get_gene_set_store
from pathfinder.services.gene_sets.types import GeneSet

logger = get_logger(__name__)


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


async def auto_import_gene_sets(
    conversations: list[ConversationWithStrategy],
    *,
    conv_repo: ConversationRepository,
    gene_set_service: GeneSetService,
    site_id: str,
    user_id: UUID,
) -> list[GeneSet]:
    """Create gene sets for eligible conversations.

    For each eligible conversation (has wdk_strategy_id, not yet imported, no
    existing gene set), creates a gene set and links it to the conversation.

    Returns the list of newly created gene sets.
    """
    created: list[GeneSet] = []

    seen_wdk_ids: set[int] = set()

    for conversation, strategy in conversations:
        if not _is_eligible(strategy):
            continue

        wdk_id = strategy.wdk_strategy_id
        if wdk_id is None:
            msg = "wdk_id must not be None (guaranteed by _is_eligible)"
            raise InternalError(detail=msg)

        if wdk_id in seen_wdk_ids:
            continue
        seen_wdk_ids.add(wdk_id)

        # Skip if a gene set already exists for this WDK strategy (from a
        # concurrent background task or previous partial import).
        existing = gene_set_service.find_by_wdk_strategy(user_id, wdk_id)
        if existing:
            await conv_repo.update_conversation(
                conversation.id,
                ConversationUpdate(
                    gene_set_id=existing.id,
                    gene_set_id_set=True,
                    gene_set_auto_imported=True,
                ),
            )
            continue

        try:
            gs = await gene_set_service.create(
                user_id=user_id,
                name=conversation.name or f"WDK Strategy {wdk_id}",
                site_id=site_id,
                gene_ids=[],
                source="strategy",
                wdk=GeneSetWdkContext(
                    wdk_strategy_id=wdk_id,
                    record_type=strategy.record_type,
                ),
            )
            await gene_set_service.flush(gs.id)
            await conv_repo.update_conversation(
                conversation.id,
                ConversationUpdate(
                    gene_set_id=gs.id,
                    gene_set_id_set=True,
                    gene_set_auto_imported=True,
                ),
            )
            created.append(gs)
            logger.info(
                "Auto-imported gene set for chat",
                gene_set_id=gs.id,
                wdk_strategy_id=wdk_id,
                gene_count=len(gs.gene_ids),
            )
        except EmptyGeneSetError:
            # Expected, not a failure: leave the latch off so a later build
            # that actually returns genes still gets imported.
            logger.info(
                "Skipped gene set auto-import: strategy returned 0 genes",
                wdk_strategy_id=wdk_id,
            )
        except (AppError, VEuPathDBError, RuntimeError) as exc:
            logger.warning(
                "Failed to auto-import gene set for chat",
                wdk_strategy_id=wdk_id,
                error=str(exc),
            )

    return created


async def import_gene_set_for_conversation(
    *,
    conversation_id: UUID,
    site_id: str,
    user_id: UUID,
) -> GeneSet | None:
    """Create + link a gene set for a single just-built conversation.

    Called inline after an auto-build commits ``wdk_strategy_id``, so a fresh
    session sees it. Idempotent (``_is_eligible`` + ``find_by_wdk_strategy``).
    Returns the created gene set, or ``None`` if ineligible/already imported.
    """
    async with async_session_factory() as session:
        try:
            repo = ConversationRepository(session)
            found = await repo.get_with_strategy(conversation_id)
            if found is None:
                return None
            conversation, strategy = found
            gene_set_svc = GeneSetService(get_gene_set_store())
            if (
                strategy.gene_set_id is not None
                and strategy.wdk_strategy_id is not None
            ):
                # Already linked → re-resolve from the (rebuilt) strategy so a
                # re-run that changed the result replaces the stale snapshot.
                resynced = await gene_set_svc.resync_strategy(
                    strategy.gene_set_id,
                    wdk_strategy_id=strategy.wdk_strategy_id,
                    site_id=site_id,
                )
                await session.commit()
                return resynced
            created = await auto_import_gene_sets(
                [(conversation, strategy)],
                conv_repo=repo,
                gene_set_service=gene_set_svc,
                site_id=site_id,
                user_id=user_id,
            )
            await session.commit()
        except (AppError, VEuPathDBError, RuntimeError) as e:
            await session.rollback()
            logger.warning(
                "Gene set auto-import for conversation failed",
                conversation_id=str(conversation_id),
                error=str(e),
            )
            return None
        return created[0] if created else None
