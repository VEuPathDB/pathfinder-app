"""The reply a card call carries: the text the researcher reads above the card."""

from __future__ import annotations

from typing import Annotated

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, StringConstraints

PROSE_MAX_CHARS = 4000
# A reply shorter than a sentence answers nothing.
_REPLY_MIN_CHARS = 20

CardReply = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=_REPLY_MIN_CHARS, max_length=PROSE_MAX_CHARS
    ),
    Field(
        description=(
            "Your reply to the message, which the researcher reads above the "
            "card: what you found, what you recommend and why. Plain markdown. "
            "It is the whole reply of this turn, so never write it as text too."
        ),
    ),
]


class CardCallReply(CamelModel):
    """The reply one card call carries, read off its arguments."""

    model_config = ConfigDict(extra="ignore")

    reply: str = ""


__all__ = ["PROSE_MAX_CHARS", "CardCallReply", "CardReply"]
