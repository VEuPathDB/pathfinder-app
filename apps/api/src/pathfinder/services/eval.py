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
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import (
    WDKDatasetConfigIdList,
    WDKDatasetIdListContent,
    get_strategy_api,
)

from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.experiment.materialization import (
    _materialize_step_tree,
)
from pathfinder.services.gene_sets.step_genes import fetch_all_gene_ids
from pathfinder.services.strategies.wdk_sync import ChatOwner, sync_to_chat

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


async def _provision_datasets(
    api: Any,
    step_tree: dict[str, Any],
    dataset_gene_ids: dict[str, list[str]] | None,
) -> None:
    """Create WDK datasets for any ds_gene_ids params and replace IDs in-place.

    Gold strategies may reference user-specific dataset IDs (e.g. curated
    gene ID lists). This function creates fresh datasets under the current
    user and patches the step tree with the new IDs.
    """
    if not dataset_gene_ids:
        return

    # Create each dataset and build old->new ID mapping
    id_map: dict[str, str] = {}
    for param_name, gene_ids in dataset_gene_ids.items():
        config = WDKDatasetConfigIdList(
            source_type="idList",
            source_content=WDKDatasetIdListContent(ids=gene_ids),
        )
        new_id = await api.create_dataset(config)
        id_map[param_name] = str(new_id)
        logger.info(
            "Created dataset for gold strategy",
            param_name=param_name,
            gene_count=len(gene_ids),
            dataset_id=new_id,
        )

    # Walk the step tree and replace dataset IDs
    def _patch(node: dict[str, Any]) -> None:
        params = node.get("parameters", {})
        for param_name, new_id in id_map.items():
            if param_name in params:
                params[param_name] = new_id
        if node.get("primaryInput"):
            _patch(node["primaryInput"])
        if node.get("secondaryInput"):
            _patch(node["secondaryInput"])

    _patch(step_tree)


async def build_gold_strategy(
    *,
    gold_id: str,
    site_id: str,
    record_type: str,
    step_tree: dict[str, Any],
    dataset_gene_ids: dict[str, list[str]] | None = None,
    user_id: UUID | None = None,
) -> GoldStrategyResult:
    """Materialize a gold strategy AST on WDK and fetch all result gene IDs.

    1. Provisions any user-specific datasets (gene ID lists).
    2. Recursively creates WDK steps from the step tree.
    3. Wraps them in a WDK strategy.
    4. Fetches all gene IDs from the root step via standard report.
    5. Returns the gene IDs plus WDK IDs.
    """
    api = get_strategy_api(site_id)

    await _provision_datasets(api, step_tree, dataset_gene_ids)

    tree_node = StrategyStepNode.model_validate(step_tree)
    root_tree = await _materialize_step_tree(api, tree_node, record_type)
    root_step_id = root_tree.step_id

    created = await api.create_strategy(
        step_tree=root_tree,
        name=f"gold:{gold_id}",
        description=f"Gold strategy: {gold_id}",
        is_saved=False,
    )
    wdk_strategy_id = created.id

    logger.info(
        "Built gold strategy on WDK",
        gold_id=gold_id,
        wdk_strategy_id=wdk_strategy_id,
        root_step_id=root_step_id,
    )

    gene_ids = await fetch_all_gene_ids(api, root_step_id)

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
                    assistant_id=PATHFINDER_ASSISTANT_ID,
                ),
                created_here=True,
            )
            await db.commit()
            conversation_id = conversation.id
        logger.info(
            "Linked gold strategy to PathFinder chat",
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
    """Fetch gene IDs for a PathFinder strategy's linked WDK root step."""
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
