"""A message the researcher sends while a card waits reaches the Lead whole:
its files with its text, and a message of files alone is a reply too."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import PendingApproval
from pydantic_ai import BinaryImage
from pydantic_ai.ui.vercel_ai.request_types import FileUIPart, TextUIPart

from pathfinder.ai.graph._lead_answers import typed_reply
from pathfinder.ai.graph._lead_turn import TurnResumption
from pathfinder.ai.graph.lead_node import _run_prompt
from pathfinder.ai.graph.state import PipelineState

_PNG_URL = "data:image/png;base64,iVBORw0KGgo="
_FILE = FileUIPart(media_type="image/png", filename="table.png", url=_PNG_URL)


def _replying(*, text: str, with_file: bool) -> PipelineState:
    """A thread whose card waits, answered by a new message instead of a click."""
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt=text,
        user_message_id=uuid4(),
    )
    state.user_parts = [
        *([_FILE] if with_file else []),
        *([TextUIPart(text=text, state="done")] if text else []),
    ]
    state.pending_approval = PendingApproval(
        phase="lead",
        tool_call_id="call_card",
        tool_name="propose_changes",
        tool_args={},
        prior_messages_json="[]",
        user_message_id=uuid4(),
    )
    return state


def test_a_message_of_files_alone_is_a_reply_with_empty_text() -> None:
    assert typed_reply(_replying(text="", with_file=True)) == ""


def test_the_reply_reaches_the_lead_with_its_file() -> None:
    state = _replying(text="use this table instead", with_file=True)
    resumption = TurnResumption(
        parked=state.pending_approval, user_prompt=typed_reply(state)
    )

    prompt = _run_prompt(state, resumption)

    assert not isinstance(prompt, str)
    assert prompt is not None
    assert [type(part) for part in prompt] == [BinaryImage, str]
    assert prompt[1] == "use this table instead"


def test_a_click_delivers_no_prompt() -> None:
    state = _replying(text="", with_file=False)
    resumption = TurnResumption(parked=state.pending_approval, user_prompt=None)

    assert (typed_reply(state), _run_prompt(state, resumption)) == (None, None)
