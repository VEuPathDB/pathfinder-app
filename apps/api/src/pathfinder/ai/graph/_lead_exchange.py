"""The exchange one Lead run adds to the conversation: what the researcher wrote
or answered, the reply the run showed, and the card it ended on."""

from __future__ import annotations

from assistant_core.graph.turn_state import ParkedCall
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.ai.graph._lead_capture import _LeadRunCapture
from pathfinder.ai.graph.state import PipelineState
from pathfinder.domain.exchanges import Exchange
from pathfinder.domain.reply_references import render_reply


class _OptionWords(CamelModel):
    model_config = ConfigDict(extra="ignore")

    label: str = ""


class _QuestionWords(CamelModel):
    model_config = ConfigDict(extra="ignore")

    prompt: str = ""
    options: list[_OptionWords] = Field(default_factory=list)

    def words(self) -> str:
        labels = "; ".join(o.label for o in self.options if o.label)
        return f"{self.prompt} (options: {labels})" if labels else self.prompt


class _CardWords(CamelModel):
    """The words a card call shows the researcher, read off its arguments."""

    model_config = ConfigDict(extra="ignore")

    reply: str = ""
    question: str = ""
    questions: list[_QuestionWords] = Field(default_factory=list)

    def asked(self, tool_name: str) -> str:
        asked = [q.words() for q in self.questions if q.prompt]
        if self.question:
            asked.append(self.question)
        return " ".join(asked) or f"approve {tool_name}"


def _answer_words(state: PipelineState, card: ParkedCall) -> str:
    """The researcher's answer to the card: the words a question card recorded,
    else yes or no with the comment they sent."""
    answered = state.turn_markers.answered
    if answered is not None and answered.on_card:
        return answered.answer
    response = state.approval_responses[card.tool_call_id]
    verdict = "yes" if response.approved else "no"
    return f"{verdict}: {response.reason}" if response.reason else verdict


def turn_exchange(state: PipelineState, capture: _LeadRunCapture) -> Exchange:
    """The exchange of this run, each reference of its reply rendered from the
    facts the turn showed."""
    card = capture.pending_approval
    words = _CardWords.model_validate(card.tool_args) if card else _CardWords()
    prose = capture.response.prose if capture.response else words.reply
    shown = render_reply(prose, capture.facts) if prose else ""
    asked = words.asked(card.tool_name) if card else ""
    answered = capture.answered_call
    if answered is None:
        return Exchange(said=state.user_prompt, reply=shown, card=asked)
    if answered.tool_call_id in state.approval_responses:
        return Exchange(
            kind="card_answer",
            said=_answer_words(state, answered),
            reply=shown,
            card=asked,
        )
    return Exchange(kind="task_result", reply=shown, card=asked)


__all__ = ["turn_exchange"]
