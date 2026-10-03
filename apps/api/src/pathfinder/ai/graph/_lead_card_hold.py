"""The card calls of a Lead run, held until the run ends and then written
each after its reply rendered from the turn's facts; a denied card is dropped."""

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
from pathfinder.domain.reply_references import render_reply
from pathfinder.domain.turn_facts import TurnFacts

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


def _reply_of(call_id: str, card: list[BaseChunk], facts: TurnFacts) -> list[BaseChunk]:
    """The card's reply rendered as text chunks, or nothing when the call
    carries none."""
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
        TextDeltaChunk(id=text_id, delta=render_reply(reply, facts)),
        TextEndChunk(id=text_id),
    ]


@dataclass
class CardHold:
    """The card calls a run has not released yet.

    ``resumed`` names the calls a resumed run re-announces: those were shown
    on the turn that made them, so they pass.
    """

    resumed: Collection[str] = ()
    _cards: dict[str, list[BaseChunk]] = field(default_factory=dict)
    _dropped: set[str] = field(default_factory=set)

    def admit(self, chunk: BaseChunk) -> list[BaseChunk]:
        """The chunks to write now, this one included when it is not held."""
        if isinstance(chunk, ToolOutputDeniedChunk) and (
            chunk.tool_call_id in self._cards or chunk.tool_call_id in self._dropped
        ):
            self._dropped.update(self._cards)
            self._cards.clear()
            return []
        if isinstance(chunk, _TEXT):
            return []
        if isinstance(chunk, _CallChunk) and self._holds(chunk):
            self._cards[chunk.tool_call_id].append(chunk)
            return []
        return [chunk]

    def holds_a_card(self) -> bool:
        return bool(self._cards)

    def release(self, facts: TurnFacts) -> list[BaseChunk]:
        """Each held card whole, after its reply, in the order they began."""
        cards = [
            chunk
            for call_id, card in self._cards.items()
            for chunk in (*_reply_of(call_id, card, facts), *card)
        ]
        self._cards.clear()
        return cards

    def _holds(self, chunk: _CallChunk) -> bool:
        if (
            isinstance(chunk, ToolInputStartChunk)
            and chunk.tool_name in CARD_TOOLS
            and chunk.tool_call_id not in self.resumed
        ):
            self._cards.setdefault(chunk.tool_call_id, [])
        return chunk.tool_call_id in self._cards


__all__ = ["CardHold"]
