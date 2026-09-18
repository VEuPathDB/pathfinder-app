"""Fetches WDK strategies and syncs them into the local conversation records."""

from dataclasses import dataclass, field
from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import StrategyAst, walk
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import StrategyAPI, get_strategy_api
from veupathdb_mcp.wdk import (
    build_snapshot_from_wdk,
    canonicalize_synced_parameters,
)

from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
)
from pathfinder.persistence.repositories.saved_strategy import (
    SavedStrategyRepository,
)
from pathfinder.platform.errors import InternalError

logger = get_logger(__name__)


@dataclass(frozen=True)
class ChatOwner:
    """The account a synced WDK strategy lands under, and its assistant."""

    user_id: UUID
    assistant_id: str


@dataclass
class WdkChatSpec:
    """The strategy fields that an upsert needs."""

    wdk_id: int
    name: str
    strategy_ast: StrategyAst
    record_type: str | None
    is_saved: bool
    step_count: int = field(default=0)


def plan_needs_detail_fetch(strategy: ConversationStrategyView) -> bool:
    """Reports whether a chat still needs its full detail from WDK. A chat with a WDK
    strategy id and no plan data holds summary data only. A local chat never needs it.
    """
    if strategy.wdk_strategy_id is None:
        return False
    ast = strategy.strategy_ast
    if not ast:
        return True
    return "root" not in ast


async def fetch_and_convert(
    api: StrategyAPI,
    wdk_id: int,
) -> tuple[StrategyAst, bool]:
    """Fetches a WDK strategy and converts it to the internal payload. Parameter
    normalization failures are logged, and the raw values are kept."""
    wdk_strategy = await api.get_strategy(wdk_id)

    payload, wire_by_step_id = build_snapshot_from_wdk(wdk_strategy)

    try:
        await canonicalize_synced_parameters(payload, api, wire_by_step_id)
    except VEuPathDBError as exc:
        logger.warning(
            "Parameter normalization failed, storing raw values",
            wdk_id=wdk_id,
            error=str(exc),
        )

    return payload, wdk_strategy.is_saved


async def sync_to_chat(
    *,
    wdk_id: int,
    site_id: str,
    api: StrategyAPI,
    conv_repo: ConversationRepository,
    owner: ChatOwner,
    created_here: bool,
) -> Conversation:
    """Fetches one WDK strategy and upserts it into the local records.

    ``created_here`` states whether the caller minted this strategy on
    VEuPathDB just before adopting it.
    """
    payload, is_saved = await fetch_and_convert(api, wdk_id)
    name = payload.name or f"WDK Strategy {wdk_id}"

    return await upsert_chat(
        conv_repo=conv_repo,
        owner=owner,
        site_id=site_id,
        created_here=created_here,
        spec=WdkChatSpec(
            wdk_id=wdk_id,
            name=name,
            strategy_ast=payload,
            record_type=payload.record_type,
            is_saved=is_saved,
            step_count=len(walk(payload.root)),
        ),
    )


async def upsert_chat(
    *,
    conv_repo: ConversationRepository,
    owner: ChatOwner,
    site_id: str,
    spec: WdkChatSpec,
    created_here: bool,
) -> Conversation:
    """Creates or updates the local record for a WDK strategy.

    A row that already names this strategy holds its provenance, so only a
    new row records ``created_here``.
    """
    found = await SavedStrategyRepository(conv_repo.session).get_by_wdk_strategy_id(
        owner.user_id, spec.wdk_id
    )
    existing = None if found is None else found[0]
    if existing:
        await conv_repo.update_conversation(
            existing.id,
            ConversationUpdate(
                name=spec.name,
                strategy_ast=spec.strategy_ast,
                record_type=spec.record_type,
                wdk_strategy_id=spec.wdk_id,
                wdk_strategy_id_set=True,
                is_saved=spec.is_saved,
                is_saved_set=True,
                step_count=spec.step_count,
            ),
        )
        conversation = await conv_repo.get_by_id(existing.id)
    else:
        created = await conv_repo.create(
            user_id=owner.user_id,
            site_id=site_id,
            assistant_id=owner.assistant_id,
            name=spec.name,
        )
        await conv_repo.update_conversation(
            created.id,
            ConversationUpdate(
                strategy_ast=spec.strategy_ast,
                record_type=spec.record_type,
                wdk_strategy_id=spec.wdk_id,
                wdk_strategy_id_set=True,
                wdk_strategy_created_here=created_here,
                wdk_strategy_created_here_set=True,
                is_saved=spec.is_saved,
                is_saved_set=True,
                step_count=spec.step_count,
            ),
        )
        conversation = await conv_repo.get_by_id(created.id)

    if conversation is None:
        msg = f"Conversation disappeared for WDK strategy {spec.wdk_id}"
        raise InternalError(detail=msg)
    return conversation


async def lazy_fetch_wdk_detail(
    *,
    conversation: Conversation,
    strategy: ConversationStrategyView,
    conv_repo: ConversationRepository,
) -> ConversationWithStrategy:
    """Fetches the full WDK detail for a chat that holds summary data only.

    Returns the updated chat, or the original one when no fetch is needed or the
    fetch fails.
    """
    site_id = conversation.site_id
    wdk_id = strategy.wdk_strategy_id
    if not plan_needs_detail_fetch(strategy) or not site_id or wdk_id is None:
        return conversation, strategy

    try:
        api = get_strategy_api(site_id)
        payload, is_saved = await fetch_and_convert(api, wdk_id)
        await conv_repo.update_conversation(
            conversation.id,
            ConversationUpdate(
                strategy_ast=payload,
                record_type=payload.record_type,
                step_count=len(walk(payload.root)),
                is_saved=is_saved,
                is_saved_set=True,
                touch_updated_at=False,
            ),
        )
        updated = await conv_repo.get_with_strategy(conversation.id)
        if updated is not None:
            return updated
    except (VEuPathDBError, RuntimeError) as exc:
        logger.warning(
            "Lazy WDK detail fetch failed",
            conversation_id=str(conversation.id),
            wdk_id=wdk_id,
            error=str(exc),
        )

    return conversation, strategy


async def sync_is_saved_to_wdk(
    *,
    conversation: Conversation,
    strategy: ConversationStrategyView,
) -> None:
    """Sends the isSaved flag from a chat to WDK. A chat with no WDK strategy id or
    site id is skipped, and a failure is logged only."""
    wdk_id = strategy.wdk_strategy_id
    if not wdk_id:
        return

    site_id = conversation.site_id
    if not site_id:
        return

    try:
        api = get_strategy_api(site_id)
        await api.set_saved(wdk_id, is_saved=strategy.is_saved)
    except VEuPathDBError as exc:
        logger.warning(
            "Failed to sync isSaved to WDK",
            conversation_id=str(conversation.id),
            wdk_id=wdk_id,
            error=str(exc),
        )
