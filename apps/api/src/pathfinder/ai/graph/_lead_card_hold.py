"""Hold a card turn's reply until the turn contract has read it.

A card call carries the turn's reply as its ``reply`` argument. Every card of
a response waits: cards the contract denies are dropped, and cards it passes
are written when the run ends, each after its reply as text.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, field

from pydantic_ai.ui.vercel_ai.response_types import (
    BaseChunk,
    TextDeltaChunk,
    TextEndChunk,
    TextStartChunk,
    ToolApprovalRequestChunk,
    ToolInputAvailableChunk,
    ToolInputDeltaChunk,
    ToolInputErrorChunk,
    ToolInputStartChunk,
    ToolOutputAvailableChunk,
    ToolOutputDeniedChunk,
    ToolOutputErrorChunk,
)

from pathfinder.ai.lead.card_contract import CARD_TOOLS
from pathfinder.ai.lead.card_reply import CardCallReply

_TEXT = (TextStartChunk, TextDeltaChunk, TextEndChunk)
_CallChunk = (
    ToolInputStartChunk
    | ToolInputDeltaChunk
    | ToolInputAvailableChunk
    | ToolInputErrorChunk
    | ToolApprovalRequestChunk
    | ToolOutputAvailableChunk
    | ToolOutputErrorChunk
)


def _reply_of(call_id: str, card: list[BaseChunk]) -> list[BaseChunk]:
    """The card's reply as text chunks, or nothing when the call carries none."""
    reply = next(
        (
            CardCallReply.model_validate(chunk.input).reply
            for chunk in card
            if isinstance(chunk, ToolInputAvailableChunk)
        ),
        "",
    )
    if not reply:
        return []
    text_id = f"reply-{call_id}"
    return [
        TextStartChunk(id=text_id),
        TextDeltaChunk(id=text_id, delta=reply),
        TextEndChunk(id=text_id),
    ]


@dataclass
class CardHold:
    """The text and the card calls a run has not released yet.

    ``resumed`` names the calls a resumed run re-announces: those were shown
    on the turn that made them, so they pass.
    """

    resumed: Collection[str] = ()
    _text: list[BaseChunk] = field(default_factory=list)
    _cards: dict[str, list[BaseChunk]] = field(default_factory=dict)
    _dropped: set[str] = field(default_factory=set)

    def admit(self, chunk: BaseChunk) -> list[BaseChunk]:
        """The chunks to write now, this one included when it is not held."""
        if isinstance(chunk, ToolOutputDeniedChunk) and (
            chunk.tool_call_id in self._cards or chunk.tool_call_id in self._dropped
        ):
            self._dropped.update(self._cards)
            self._text.clear()
            self._cards.clear()
            return []
        if isinstance(chunk, _TEXT):
            self._text.append(chunk)
            return []
        if isinstance(chunk, _CallChunk) and self._holds(chunk):
            self._cards[chunk.tool_call_id].append(chunk)
            return []
        if self._cards:
            return [chunk]
        return [*self.release(), chunk]

    def release(self) -> list[BaseChunk]:
        """The held text, then each held card whole, in the order they began.

        A card's reply replaces any text written beside it, so the reply the
        contract read is the only reply the researcher reads.
        """
        text = [] if self._cards else list(self._text)
        cards = [
            chunk
            for call_id, card in self._cards.items()
            for chunk in (*_reply_of(call_id, card), *card)
        ]
        self._text.clear()
        self._cards.clear()
        return [*text, *cards]

    def _holds(self, chunk: _CallChunk) -> bool:
        if (
            isinstance(chunk, ToolInputStartChunk)
            and chunk.tool_name in CARD_TOOLS
            and chunk.tool_call_id not in self.resumed
        ):
            self._cards.setdefault(chunk.tool_call_id, [])
        return chunk.tool_call_id in self._cards


__all__ = ["CardHold"]
