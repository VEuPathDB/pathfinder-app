"""Conversation request/response DTOs — unified chat + strategy shape."""

from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.transport.http.schemas.site_id import SiteId


class StepCountsRequest(CamelModel):
    site_id: SiteId
    strategy_ast: StrategyAst


class StepCountsResponse(CamelModel):
    counts: dict[str, int | None]


class OpenConversationRequest(CamelModel):
    conversation_id: UUID | None = Field(default=None)
    wdk_strategy_id: int | None = Field(default=None)
    site_id: SiteId | None = Field(default=None)


class OpenConversationResponse(CamelModel):
    conversation_id: UUID


class BeginConversationRequest(CamelModel):
    site_id: SiteId
    experiment_id: str | None = None
    seed_text: str | None = Field(default=None, max_length=4000)
    # Names the assistant a NEW conversation is created under. An existing
    # conversation keeps its own, and a request naming another one is refused.
    assistant_id: str | None = Field(default=None, max_length=64)


class BeginConversationResponse(CamelModel):
    conversation_id: UUID
    is_new: bool
    name: str


class CreateConversationRequest(CamelModel):
    name: str = Field(min_length=1, max_length=255)
    site_id: SiteId
    strategy_ast: StrategyAst


class UpdateConversationRequest(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    strategy_ast: StrategyAst | None = Field(default=None)
    wdk_strategy_id: int | None = Field(default=None)
    is_saved: bool | None = Field(default=None)


class PushConversationRequest(CamelModel):
    name: str = Field(min_length=1, max_length=255)
    site_id: SiteId
    strategy_ast: StrategyAst
    description: str | None = Field(default=None, max_length=2000)


class ConversationPatchBody(CamelModel):
    """Sidebar patch payload — rename / toggle saved."""

    name: str | None = None
    is_saved: bool | None = Field(default=None)


class ConversationDuplicateResponse(CamelModel):
    id: UUID
    name: str


class SaveSubstrategyRequest(CamelModel):
    """POST body for saving a subtree of the active strategy."""

    step_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class SaveSubstrategyResponse(CamelModel):
    wdk_strategy_id: int
    name: str
    description: str | None = None
    record_type: str
    root_step_id: int


class ForkConversationRequest(CamelModel):
    from_message_id: UUID
