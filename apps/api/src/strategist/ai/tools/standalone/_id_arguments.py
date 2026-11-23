"""The Strategist ids a tool argument names, each a UUID."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from pydantic import Field

_NOT_A_WDK_ID = "A WDK strategy or step id is a different id and does not work here."

ControlSetId = Annotated[
    UUID,
    Field(description=f"A Strategist control set id, a UUID. {_NOT_A_WDK_ID}"),
]
ConversationId = Annotated[
    UUID,
    Field(description=f"A Strategist conversation id, a UUID. {_NOT_A_WDK_ID}"),
]
