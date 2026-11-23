"""Thesis evaluation service.

Business logic for materializing gold strategies and fetching gene IDs.
The transport layer (``transport.http.routers.evaluation``) is a thin HTTP
adapter that delegates to this module.
"""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from assistant_core.conversation.authz import get_visible_conversation
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.logging import get_logger
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.errors import ValidationError
from veupathdb.wdk import (
    get_strategy_api,
)

from strategist.domain.strategy.operations.apply import ApplyError
from strategist.persistence.repositories.conversation import ConversationRepository
from strategist.platform.identity import STRATEGIST_ASSISTANT_ID
from strategist.services.gene_sets.step_genes import (
    TooManyGenesError,
    fetch_all_gene_ids,
)
from strategist.services.strategies.commit_tree import CommitTarget, commit_tree
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.services.strategies.wdk_sync import ChatOwner, sync_to_chat

logger = get_logger(__name__)


class StrategyGeneIdsResult(CamelModel):
    """Gene IDs behind a strategy's WDK root step, or why there are none."""

    gene_ids: list[str] = Field(default_factory=list)
    estimated_size: int | None = None
    error: str | None = None


@dataclass(frozen=True)
class GoldStrategyResult:
    """Result of materializing a gold strategy on WDK."""

    gold_id: str
    wdk_strategy_id: int
    root_step_id: int
    gene_ids: list[str]
    conversation_id: UUID | None = None


async def build_gold_strategy(
    *,
    gold_id: str,
    site_id: str,
    step_tree: dict[str, Any],
    dataset_gene_ids: dict[str, list[str]] | None = None,
    user_id: UUID | None = None,
) -> GoldStrategyResult:
    """Materialize a gold strategy AST on WDK and fetch all result gene IDs.

    1. Provisions any user-specific datasets (gene ID lists).
    2. Commits the tree through the one commit path as an internal strategy,
       which refuses a tree the site cannot run and keeps nothing it refused.
    3. Fetches all gene IDs from the root step via standard report.
    4. Returns the gene IDs plus WDK IDs.
    """
    api = get_strategy_api(site_id)
    tree_node = StrategyStepNode.model_validate(step_tree)

    sync_state = WDKSyncState()
    try:
        committed = await commit_tree(
            site_id=site_id,
            steps=flatten_tree(tree_node),
            root_id=tree_node.id,
            old=None,
            sync_state=sync_state,
            target=CommitTarget(
                name=f"gold:{gold_id}",
                description=f"Gold strategy: {gold_id}",
                role="internal",
                datasets=dataset_gene_ids or {},
            ),
        )
    except ApplyError as exc:
        raise ValidationError(
            title="The site cannot run this tree", detail=str(exc)
        ) from exc
    if committed.sync is None or committed.refused or not committed.put:
        raise ValidationError(
            title="The site did not build the gold strategy",
            detail="; ".join(
                f"step {sid!r}: {text}" for sid, text in committed.refused.items()
            )
            or "the site took no strategy",
        )
    root_step_id = committed.sync.root_step_id
    wdk_strategy_id = committed.sync.wdk_strategy_id

    logger.info(
        "Built gold strategy on WDK",
        gold_id=gold_id,
        wdk_strategy_id=wdk_strategy_id,
        root_step_id=root_step_id,
    )

    try:
        gene_ids = await fetch_all_gene_ids(api, root_step_id)
    except TooManyGenesError:
        await api.delete_strategy(wdk_strategy_id)
        raise

    conversation_id: UUID | None = None
    if user_id is not None:
        async with async_session_factory() as db:
            conversation = await sync_to_chat(
                wdk_id=wdk_strategy_id,
                site_id=site_id,
                api=api,
                conv_repo=ConversationRepository(db),
                owner=ChatOwner(
                    user_id=user_id,
                    assistant_id=STRATEGIST_ASSISTANT_ID,
                ),
                created_here=True,
            )
            await db.commit()
            conversation_id = conversation.id
        logger.info(
            "Linked gold strategy to Strategist chat",
            gold_id=gold_id,
            conversation_id=str(conversation_id),
        )

    return GoldStrategyResult(
        gold_id=gold_id,
        wdk_strategy_id=wdk_strategy_id,
        root_step_id=root_step_id,
        gene_ids=gene_ids,
        conversation_id=conversation_id,
    )


async def fetch_strategy_gene_ids(
    *,
    api: Any,
    wdk_strategy_id: int,
) -> list[str]:
    """Fetch all gene IDs from a chat's linked WDK strategy.

    :param api: StrategyAPI instance for the site.
    :param wdk_strategy_id: the WDK strategy the chat is linked to.
    :returns: List of gene ID strings.
    """
    strategy = await api.get_strategy(wdk_strategy_id)
    return await fetch_all_gene_ids(api, strategy.root_step_id)


async def get_strategy_gene_ids(
    session: AsyncSession,
    strategy_id: UUID,
    site_id: str,
    user_id: UUID,
) -> StrategyGeneIdsResult:
    """Fetch gene IDs for a Strategist strategy's linked WDK root step."""
    repo = ConversationRepository(session)
    conversation = await get_visible_conversation(repo, strategy_id, user_id)
    strategy = await repo.get_strategy(conversation.id)
    if not strategy.wdk_strategy_id:
        return StrategyGeneIdsResult(error="No WDK strategy linked")
    api = get_strategy_api(site_id)
    gene_ids = await fetch_strategy_gene_ids(
        api=api,
        wdk_strategy_id=strategy.wdk_strategy_id,
    )
    if not gene_ids:
        return StrategyGeneIdsResult(error="No gene IDs found")
    return StrategyGeneIdsResult(gene_ids=gene_ids, estimated_size=len(gene_ids))
