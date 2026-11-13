"""The reply a card call carries: the text the researcher reads above the card."""

from __future__ import annotations

from typing import Annotated

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, StringConstraints

PROSE_MAX_CHARS = 4000
# A reply shorter than a sentence answers nothing.
_REPLY_MIN_CHARS = 20
CITABLE_RECORDS = (
    "a record this turn read, listed, checked or resolved, or one of the "
    "records the conversation showed last"
)
REPLY_NOTE = (
    "It is a note beside the facts the product writes. The facts show each "
    "count, value, setting, step, record, link and check of this turn as the "
    "site holds it, so the note restates none of them: it says what they mean "
    "for the question, why this reading answers it, and what to do next. It "
    "writes no number of this turn: no count, value, percent or setting. A "
    "name is written as it stands, letters and digits together: a strain such "
    "as 3D7, a gene symbol, a tool and its version. A record is named as "
    f"[record:<record_id>], which links {CITABLE_RECORDS}; any other record "
    "reference is dropped. A turn that read nothing from a site shows no "
    "facts, and its note writes freely."
)

CardReply = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=_REPLY_MIN_CHARS, max_length=PROSE_MAX_CHARS
    ),
    Field(
        description=(
            "Your reply to the message, which the researcher reads above the "
            "card: what you found, what you recommend and why. Plain markdown. "
            "It is the whole reply of this turn, so never write it as text too. "
            f"{REPLY_NOTE}"
        ),
    ),
]


# A refused card never reached the researcher, so no reply speaks of it.
CARD_NOT_SHOWN = "The researcher never saw this card, so the reply does not mention it."


class CardCallReply(CamelModel):
    """The reply one card call carries, read off its arguments."""

    model_config = ConfigDict(extra="ignore")

    reply: str = ""


__all__ = [
    "CARD_NOT_SHOWN",
    "CITABLE_RECORDS",
    "PROSE_MAX_CHARS",
    "REPLY_NOTE",
    "CardCallReply",
    "CardReply",
]
