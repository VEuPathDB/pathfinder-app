"""Hold a card turn's reply until the turn contract has read it.

The Lead's text streams before the calls it precedes. When a call is a card,
the text and every card of the response wait: cards the contract denies are
dropped with their text, and cards it passes are written when the run ends.
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
        """The held text, then each held card whole, in the order they began."""
        held = [*self._text, *(c for card in self._cards.values() for c in card)]
        self._text.clear()
        self._cards.clear()
        return held

    def _holds(self, chunk: _CallChunk) -> bool:
        if (
            isinstance(chunk, ToolInputStartChunk)
            and chunk.tool_name in CARD_TOOLS
            and chunk.tool_call_id not in self.resumed
        ):
            self._cards.setdefault(chunk.tool_call_id, [])
        return chunk.tool_call_id in self._cards


__all__ = ["CardHold"]
