"""Conversation response DTOs + builders.

Owns the ``Conversation`` ORM -> response-DTO mapping so transport returns
these without importing persistence or building them itself.
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from assistant_core.persistence.models import Conversation
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from veupathdb.domain.strategy import StrategyAst, walk
from veupathdb.errors import SiteNotFoundError
from veupathdb.wdk import get_site

from pathfinder.domain.strategy.revision import (
    parse_strategy_ast,
    strategy_revision,
)
from pathfinder.persistence.models import ConversationStrategyView
from pathfinder.persistence.repositories.conversation_strategy import (
    ConversationWithStrategy,
)
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.strategies.schemas import (
    StepResponse,
    step_response_from_strategy_ast,
)


class StepRecord(CamelModel):
    """One gene a step answers, and the page where the site shows it."""

    gene_id: str
    organism: str | None
    product: str | None
    record_url: str


class StepRecordsResponse(CamelModel):
    """One page of the genes a pushed step answers on its site."""

    step_id: str
    wdk_step_id: int
    total: int
    offset: int
    limit: int
    record_type: str
    step_url: str
    records: list[StepRecord]


class ConversationResponse(CamelModel):
    id: UUID
    name: str
    title: str | None = None
    description: str | None = None
    assistant_id: str = PATHFINDER_ASSISTANT_ID
    site_id: str
    record_type: str | None
    steps: list[StepResponse] = Field(default_factory=list)
    root_step_id: str | None = Field(default=None)
    wdk_strategy_id: int | None = Field(default=None)
    wdk_strategy_created_here: bool = Field(default=False)
    is_saved: bool = Field(default=False)
    created_at: datetime
    updated_at: datetime
    step_count: int | None = Field(default=None)
    estimated_size: int | None = Field(default=None)
    wdk_url: str | None = Field(default=None)
    gene_set_id: str | None = Field(default=None)
    dismissed_at: datetime | None = Field(default=None)
    total_tokens: int = Field(default=0)
    total_cost_usd: Decimal = Field(default_factory=lambda: Decimal(0))
    parent_conversation_id: UUID | None = Field(default=None)
    parent_message_id: UUID | None = Field(default=None)
    strategy_revision: str = Field(default="")


def _compute_wdk_url(site_id: str, wdk_strategy_id: int | None) -> str | None:
    if wdk_strategy_id is None or not site_id:
        return None
    # A thread on a site this deployment no longer serves still lists.
    try:
        site = get_site(site_id)
    except SiteNotFoundError:
        return None
    return site.strategy_url(wdk_strategy_id)


def derive_steps_from_strategy_ast(payload: StrategyAst | None) -> list[StepResponse]:
    """Every step the canvas should draw, including ones not yet combined.

    Detached components are part of what the researcher is working on even
    though they are not in the pushed tree; leaving them out here makes them
    disappear from the graph on the next read.
    """
    if payload is None:
        return []
    nodes = list(walk(payload.root))
    for detached in payload.detached_roots:
        nodes.extend(walk(detached))
    return [step_response_from_strategy_ast(payload, step) for step in nodes]


def extract_strategy_description(payload: StrategyAst | None) -> str | None:
    if payload is None:
        return None
    return payload.description


def extract_root_step_id(
    payload: StrategyAst | None,
    fallback_root_step_id: str | None = None,
) -> str | None:
    if payload is not None:
        return payload.root.id
    return fallback_root_step_id


def conversation_strategy_revision(strategy: ConversationStrategyView | None) -> str:
    """Fingerprint the conversation's persisted strategy; ``""`` when absent."""
    if strategy is None:
        return ""
    return strategy_revision(parse_strategy_ast(strategy.strategy_ast))


def build_conversation_response(
    conversation: Conversation,
    strategy: ConversationStrategyView,
    *,
    total_tokens: int = 0,
    total_cost_usd: Decimal | None = None,
) -> ConversationResponse:
    """Build a detail-view ``ConversationResponse`` from a ``Conversation``."""
    payload = parse_strategy_ast(strategy.strategy_ast)
    root_step_id = extract_root_step_id(payload)
    wdk_url = _compute_wdk_url(conversation.site_id, strategy.wdk_strategy_id)

    return ConversationResponse(
        id=conversation.id,
        name=conversation.name,
        title=conversation.name,
        description=extract_strategy_description(payload),
        assistant_id=conversation.assistant_id,
        site_id=conversation.site_id,
        record_type=strategy.record_type,
        steps=derive_steps_from_strategy_ast(payload),
        root_step_id=root_step_id,
        wdk_strategy_id=strategy.wdk_strategy_id,
        wdk_strategy_created_here=strategy.wdk_strategy_created_here,
        wdk_url=wdk_url,
        gene_set_id=strategy.gene_set_id,
        is_saved=strategy.is_saved,
        created_at=conversation.created_at or datetime.now(UTC),
        updated_at=conversation.updated_at or datetime.now(UTC),
        dismissed_at=conversation.dismissed_at,
        total_tokens=total_tokens,
        total_cost_usd=total_cost_usd if total_cost_usd is not None else Decimal(0),
        parent_conversation_id=conversation.parent_conversation_id,
        parent_message_id=conversation.parent_message_id,
        strategy_revision=strategy_revision(payload),
    )


def build_conversation_summary(
    conversation: Conversation,
    strategy: ConversationStrategyView,
    *,
    site_id: str = "",
) -> ConversationResponse:
    """Build a list-view ``ConversationResponse`` (steps=[]) from a ``Conversation``."""
    effective_site_id = site_id or conversation.site_id
    wdk_url = _compute_wdk_url(effective_site_id, strategy.wdk_strategy_id)
    payload = parse_strategy_ast(strategy.strategy_ast)

    return ConversationResponse(
        id=conversation.id,
        name=conversation.name,
        title=conversation.name,
        description=extract_strategy_description(payload),
        assistant_id=conversation.assistant_id,
        site_id=effective_site_id,
        record_type=strategy.record_type,
        wdk_strategy_id=strategy.wdk_strategy_id,
        wdk_strategy_created_here=strategy.wdk_strategy_created_here,
        wdk_url=wdk_url,
        gene_set_id=strategy.gene_set_id,
        is_saved=strategy.is_saved,
        step_count=strategy.step_count,
        estimated_size=strategy.estimated_size,
        created_at=conversation.created_at or datetime.now(UTC),
        updated_at=conversation.updated_at or datetime.now(UTC),
        dismissed_at=conversation.dismissed_at,
        parent_conversation_id=conversation.parent_conversation_id,
        parent_message_id=conversation.parent_message_id,
        strategy_revision=strategy_revision(payload),
    )


def build_conversation_summaries(
    rows: Sequence[ConversationWithStrategy],
    *,
    site_id: str = "",
) -> list[ConversationResponse]:
    """Build the list view for a page of threads and their projections."""
    return [
        build_conversation_summary(conversation, strategy, site_id=site_id)
        for conversation, strategy in rows
    ]
