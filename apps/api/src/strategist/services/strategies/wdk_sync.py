"""Fetches WDK strategies and syncs them into the local conversation records."""

from dataclasses import dataclass, field, replace
from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import StrategyAst, walk
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import (
    StrategyAPI,
    get_strategy_api,
    strip_internal_wdk_strategy_name,
)
from veupathdb_mcp.wdk import (
    build_snapshot_from_wdk,
    canonicalize_synced_parameters,
)

from strategist.domain.strategy.combine_naming import given_by_a_researcher
from strategist.domain.strategy.step_words import StepWords
from strategist.evals.scoring import root_count
from strategist.persistence.models import ConversationStrategyView
from strategist.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from strategist.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
)
from strategist.persistence.repositories.saved_strategy import (
    SavedStrategyRepository,
)
from strategist.platform.errors import InternalError, SiteUnavailableError
from strategist.services.eda.analysis_kinds import analysis_kinds_of
from strategist.services.site_errors import site_words
from strategist.services.strategies.naming import placeholder_strategy_name

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
    *,
    site_id: str,
) -> tuple[StrategyAst, bool]:
    """Fetches a WDK strategy and converts it to the internal payload. A value no
    parameter kind reads is not normalized, and the raw values are kept.

    WDK stores no Strategist metadata, so each EDA step's analysis kind is read
    from the site's catalog here.
    """
    wdk_strategy = await api.get_strategy(wdk_id)

    payload, wire_by_step_id = build_snapshot_from_wdk(wdk_strategy)

    await canonicalize_synced_parameters(payload, api, wire_by_step_id)
    nodes = [
        node for root in (payload.root, *payload.detached_roots) for node in walk(root)
    ]
    kinds = await analysis_kinds_of(site_id=site_id, nodes=nodes)
    if kinds:
        payload.metadata = StepWords(analysis_kinds=kinds).model_dump(
            by_alias=True, mode="json"
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
    payload, is_saved = await fetch_and_convert(api, wdk_id, site_id=site_id)

    return await upsert_chat(
        conv_repo=conv_repo,
        owner=owner,
        site_id=site_id,
        created_here=created_here,
        spec=WdkChatSpec(
            wdk_id=wdk_id,
            name=wdk_chat_name(payload, wdk_id),
            strategy_ast=payload,
            record_type=payload.record_type,
            is_saved=is_saved,
            step_count=len(walk(payload.root)),
        ),
    )


def wdk_chat_name(payload: StrategyAst, wdk_id: int) -> str:
    """The strategy's name, else its root step's own name, else its id."""
    root = payload.root
    given = given_by_a_researcher(root.display_name, root.search_name)
    root_name = root.display_name if given else None
    given_name = strip_internal_wdk_strategy_name(payload.name or "")
    return given_name or root_name or placeholder_strategy_name(wdk_id)


def import_write(spec: WdkChatSpec, *, name: str) -> ConversationUpdate:
    """The strategy columns an import writes; the stored count is the root's."""
    return ConversationUpdate(
        strategy_ast=spec.strategy_ast.model_copy(update={"name": name}),
        record_type=spec.record_type,
        wdk_strategy_id=spec.wdk_id,
        wdk_strategy_id_set=True,
        is_saved=spec.is_saved,
        step_count=spec.step_count,
        estimated_size=root_count(spec.strategy_ast),
        estimated_size_set=True,
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
    new row records ``created_here``. A thread keeps the name it holds, and
    the stored strategy carries that name.
    """
    found = await SavedStrategyRepository(conv_repo.session).get_by_wdk_strategy_id(
        owner.user_id, spec.wdk_id
    )
    existing = None if found is None else found[0]
    if existing:
        write = import_write(spec, name=existing.name or spec.name)
        await conv_repo.update_conversation(
            existing.id,
            replace(write, name=None if existing.name else spec.name),
        )
        conversation = await conv_repo.get_by_id(existing.id)
    else:
        created = await conv_repo.create(
            user_id=owner.user_id,
            site_id=site_id,
            assistant_id=owner.assistant_id,
            name=spec.name,
        )
        write = import_write(spec, name=created.name)
        await conv_repo.update_conversation(
            created.id,
            replace(
                write,
                wdk_strategy_created_here=created_here,
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
        payload, is_saved = await fetch_and_convert(api, wdk_id, site_id=site_id)
        await conv_repo.update_conversation(
            conversation.id,
            ConversationUpdate(
                strategy_ast=payload,
                record_type=payload.record_type,
                step_count=len(walk(payload.root)),
                estimated_size=root_count(payload),
                estimated_size_set=True,
                is_saved=is_saved,
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


async def set_the_saved_mark(
    *, site_id: str, wdk_strategy_id: int, is_saved: bool
) -> None:
    """Set the saved mark on the WDK strategy, or refuse the change."""
    try:
        await get_strategy_api(site_id).set_saved(wdk_strategy_id, is_saved=is_saved)
    except VEuPathDBError as exc:
        logger.warning(
            "Failed to sync isSaved to WDK", wdk_id=wdk_strategy_id, error=str(exc)
        )
        raise SiteUnavailableError(
            site_id, f"the saved mark was not set: {site_words(exc)}"
        ) from exc
