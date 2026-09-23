"""Hold a card turn's reply until the turn contract has read it.

The Lead's text streams before the call it precedes. When that call is a card,
the text and the card wait: a card the contract denies is dropped with its
text, and one it passes is written when the run ends.
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
    ToolInputStartChunk,
    ToolOutputDeniedChunk,
)

from pathfinder.ai.lead.card_contract import CARD_TOOLS

_TEXT = (TextStartChunk, TextDeltaChunk, TextEndChunk)
_CARD_CALL = (
    ToolInputStartChunk,
    ToolInputDeltaChunk,
    ToolInputAvailableChunk,
    ToolApprovalRequestChunk,
)


@dataclass
class CardHold:
    """The text and the card call a run has not released yet.

    ``resumed`` names the calls a resumed run re-announces: those were shown
    on the turn that made them, so they pass.
    """

    resumed: Collection[str] = ()
    _held: list[BaseChunk] = field(default_factory=list)
    _card: str | None = None

    def admit(self, chunk: BaseChunk) -> list[BaseChunk]:
        """The chunks to write now, this one included when it is not held."""
        if (
            isinstance(chunk, ToolOutputDeniedChunk)
            and chunk.tool_call_id == self._card
        ):
            self._held.clear()
            self._card = None
            return []
        if self._holds(chunk):
            self._held.append(chunk)
            return []
        if self._card is not None:
            return [chunk]
        return [*self.release(), chunk]

    def release(self) -> list[BaseChunk]:
        """Everything held, in the order it arrived."""
        held, self._held = self._held, []
        self._card = None
        return held

    def _holds(self, chunk: BaseChunk) -> bool:
        if isinstance(chunk, _TEXT):
            return True
        if not isinstance(chunk, _CARD_CALL):
            return False
        if (
            isinstance(chunk, ToolInputStartChunk)
            and chunk.tool_name in CARD_TOOLS
            and chunk.tool_call_id not in self.resumed
        ):
            self._card = chunk.tool_call_id
        return chunk.tool_call_id == self._card


__all__ = ["CardHold"]
