"""A turn opened by a message with files carries them to the state, the files
first and the text after, as the runtime orders a user message."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.spec import TurnStart
from pydantic_ai import BinaryImage
from pydantic_ai.ui.vercel_ai.request_types import FileUIPart, TextUIPart

from pathfinder.ai.conversation._turn_helpers import build_turn_start
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.assistants.pathfinder_spec import build_initial_state

_PNG_URL = "data:image/png;base64,iVBORw0KGgo="
_TEXT = "which genes are in this image?"


def _body() -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "conversationId": str(uuid4()),
            "siteId": "plasmodb",
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [
                        {"type": "text", "text": _TEXT},
                        {
                            "type": "file",
                            "mediaType": "image/png",
                            "filename": "table.png",
                            "url": _PNG_URL,
                        },
                    ],
                },
            ],
        }
    )


def _start(body: ChatRequestBody) -> TurnStart:
    return build_turn_start(
        body, uuid4(), turn_message_id=uuid4(), turn_start_event_id=0
    )


def test_the_turn_start_carries_the_file_and_the_text() -> None:
    start = _start(_body())

    assert start.user_prompt == _TEXT
    assert [(f.filename, f.media_type, f.url) for f in start.user_files] == [
        ("table.png", "image/png", _PNG_URL)
    ]


def test_the_state_holds_the_file_before_the_text() -> None:
    state = build_initial_state(_start(_body()))

    assert state.user_parts == [
        FileUIPart(media_type="image/png", filename="table.png", url=_PNG_URL),
        TextUIPart(text=_TEXT, state="done"),
    ]
    content = state.user_content
    assert not isinstance(content, str)
    assert [type(c) for c in content] == [BinaryImage, str]
    assert content[1] == _TEXT
