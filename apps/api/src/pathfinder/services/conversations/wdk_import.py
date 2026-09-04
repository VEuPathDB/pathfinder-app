"""WDK strategy open orchestration."""

from uuid import UUID

from assistant_core.platform.logging import get_logger
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.domain.conversation import DEFAULT_STREAM_NAME
from pathfinder.integrations.veupathdb.factory import get_strategy_api
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.errors import (
    AppError,
    ErrorCode,
    NotFoundError,
    ValidationError,
    WDKError,
)
from pathfinder.services.conversations.authz import owned_by_caller
from pathfinder.services.strategies.wdk_sync import sync_to_chat

logger = get_logger(__name__)


def _require_site_id(site_id: str | None) -> str:
    if not site_id:
        raise ValidationError(
            detail="siteId is required",
            errors=[
                {"path": "siteId", "message": "Required", "code": "INVALID_PARAMETERS"},
            ],
        )
    return site_id


async def open_strategy(
    session: AsyncSession,
    *,
    conversation_id: UUID | None,
    wdk_strategy_id: int | None,
    site_id: str | None,
    user_id: UUID,
) -> UUID:
    """Open a strategy by local id or WDK strategy id; create a fresh one if neither."""
    conv_repo = ConversationRepository(session)

    if not conversation_id and not wdk_strategy_id:
        conversation = await conv_repo.create(
            user_id=user_id,
            site_id=_require_site_id(site_id),
            name=DEFAULT_STREAM_NAME,
        )
        return conversation.id

    if conversation_id:
        existing = await conv_repo.get_by_id(conversation_id)
        if not existing or not owned_by_caller(existing, user_id):
            raise NotFoundError(
                code=ErrorCode.STRATEGY_NOT_FOUND,
                title="Strategy not found",
            )
        return existing.id

    resolved_site = _require_site_id(site_id)
    if wdk_strategy_id is None:
        raise ValidationError(
            detail="wdk_strategy_id is required",
            errors=[
                {
                    "path": "wdk_strategy_id",
                    "message": "Required",
                    "code": "INVALID_PARAMETERS",
                },
            ],
        )
    # Resolving the site is the caller's business, not the upstream service's:
    # an unconfigured siteId raises NotFoundError(SITE_NOT_FOUND). Kept out of
    # the block below so a typo reports 404 instead of "VEuPathDB is down".
    api = get_strategy_api(resolved_site)
    try:
        conversation = await sync_to_chat(
            wdk_id=wdk_strategy_id,
            site_id=resolved_site,
            api=api,
            conv_repo=conv_repo,
            user_id=user_id,
        )
    except AppError:
        logger.exception("WDK fetch failed")
        raise
    except Exception as e:
        logger.exception("WDK fetch failed")
        msg = f"Failed to load WDK strategy: {e}"
        raise WDKError(msg) from e
    return conversation.id
