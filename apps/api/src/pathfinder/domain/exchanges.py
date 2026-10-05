"""The last exchanges of a conversation as the researcher read them, which the
Lead reads back on every turn."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

# The exchanges the Lead reads back; the ledger holds what is older.
EXCHANGE_WINDOW = 6

_HEADING = "## The conversation so far"
_NOTE = (
    "The last exchanges of this conversation, oldest first, as the researcher "
    "read them. A number or a record in them held when it was shown; the "
    "ledger and the facts hold the strategy now."
)

type ExchangeKind = Literal["message", "card_answer", "task_result"]


class Exchange(CamelModel):
    """One exchange: what the researcher wrote or answered, the reply they read
    with each reference rendered, and the card the reply ended on."""

    model_config = ConfigDict(frozen=True)

    kind: ExchangeKind = "message"
    said: str = ""
    reply: str = ""
    card: str = ""

    def empty(self) -> bool:
        return not (self.said or self.reply or self.card)

    def lines(self) -> list[str]:
        opening = {
            "message": f"Researcher: {self.said}",
            "card_answer": f"Researcher answered the card: {self.said}",
            "task_result": "A background task finished.",
        }[self.kind]
        return [
            opening,
            *([f"You replied: {self.reply}"] if self.reply else []),
            *([f"You asked on a card: {self.card}"] if self.card else []),
        ]


def kept_exchanges(held: Sequence[Exchange], exchange: Exchange) -> list[Exchange]:
    """The held exchanges with this one, the last ``EXCHANGE_WINDOW`` of them."""
    if exchange.empty():
        return list(held)
    return [*held, exchange][-EXCHANGE_WINDOW:]


def exchanges_section(exchanges: Sequence[Exchange]) -> str | None:
    """The exchanges as the Lead reads them, or None when there is none."""
    if not exchanges:
        return None
    blocks = ["\n".join(exchange.lines()) for exchange in exchanges]
    return "\n\n".join([f"{_HEADING}\n{_NOTE}", *blocks])


__all__ = [
    "EXCHANGE_WINDOW",
    "Exchange",
    "ExchangeKind",
    "exchanges_section",
    "kept_exchanges",
]
