"""The reply a card call carries: the text the researcher reads above the card."""

from __future__ import annotations

from typing import Annotated

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, StringConstraints

PROSE_MAX_CHARS = 4000
# A reply shorter than a sentence answers nothing.
_REPLY_MIN_CHARS = 20
PLACEMENT_RULES = (
    "A count reference renders with its noun, so no noun follows it. A number "
    "word (one to twelve, twice, two-fold) never stands in the clause of "
    "a count or value reference, which stands in place of the number."
)
# The records a record reference cites. The schema and the Lead's instruction
# both state it.
CITABLE_RECORDS = (
    "a record this turn read, listed, checked or resolved, or one of the "
    "records the conversation showed last"
)
REPLY_REFERENCES = (
    "It writes no number, identifier or link itself: each fact is a "
    "reference the product renders from the facts beside the reply. "
    "[count:<step_id>] a step's count, [before:<step_id>] its count before this "
    "turn's edit, [root] and [root_before] the result's, [last_change:before] "
    "and [last_change:after] the result's before and after the strategy's most "
    "recent change, which an earlier turn may have made, [diff:<a>,<b>] the "
    "difference of two counts (each side a step id, root, root_before, "
    "before:<step_id>, last_change:before, last_change:after or "
    "compare:<variant>), [value:<step_id>.<param>] a bound "
    "value with its label, [source:<step_id>.<param>] who set it, "
    "[compare:<variant>] the genes a comparison of this turn returned for a "
    "variant (add :unique or :result; [compare:<a>,<b>:shared] for the genes "
    f"two share), [record:<record_id>] {CITABLE_RECORDS}, [url] the strategy's "
    f"link. {PLACEMENT_RULES}"
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
            f"{REPLY_REFERENCES}"
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
    "PLACEMENT_RULES",
    "PROSE_MAX_CHARS",
    "REPLY_REFERENCES",
    "CardCallReply",
    "CardReply",
]
