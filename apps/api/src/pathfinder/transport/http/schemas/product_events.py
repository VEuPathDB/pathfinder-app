"""The product events the web reports, one shape per event."""

from typing import Annotated, Literal
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field


class _ThreadEvent(CamelModel):
    conversation_id: UUID | None = None


class CardAnswered(_ThreadEvent):
    """A consult or approval card the researcher answered."""

    event: Literal["card_answered"]
    tool_name: str
    approved: bool


class StrategyOpened(_ThreadEvent):
    """The link that opens the strategy on the VEuPathDB site."""

    event: Literal["strategy_opened"]
    site_id: str
    wdk_strategy_id: int | None = None


class ExportRequested(_ThreadEvent):
    """An export the researcher asked for."""

    event: Literal["export_requested"]
    export_kind: str


class TurnUndone(_ThreadEvent):
    """A revert of the thread to an earlier message."""

    event: Literal["turn_undone"]
    message_id: str


class AssistantRegenerated(_ThreadEvent):
    """A request to answer the last message again."""

    event: Literal["assistant_regenerated"]
    message_id: str


class SiteSwitched(_ThreadEvent):
    """A move from one VEuPathDB site to another."""

    event: Literal["site_switched"]
    from_site: str
    to_site: str


type ProductEventRequest = Annotated[
    CardAnswered
    | StrategyOpened
    | ExportRequested
    | TurnUndone
    | AssistantRegenerated
    | SiteSwitched,
    Field(discriminator="event"),
]
