"""Frame parsing in the chat SSE test helper."""

from __future__ import annotations

import json
from typing import Any

from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from pathfinder.tests.integration.chat._helpers import parse_sse_body

_LINE_SEPARATOR = "\u2028"

_STUDIES_LIST = FIXTURE_DIR / "studies_list.json"


def _recorded_description_with_line_separator() -> str:
    raw = json.loads(_STUDIES_LIST.read_text(encoding="utf-8"))
    for study in raw["studies"]:
        description = str(study["description"])
        if _LINE_SEPARATOR in description:
            return description
    msg = "studies_list.json no longer records a U+2028 description"
    raise AssertionError(msg)


def _wire(payload: dict[str, Any], event_id: int) -> str:
    """One SSE event as the event stream writes it: no ASCII escaping."""
    return f"id: {event_id}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def test_a_payload_carrying_u2028_stays_one_frame() -> None:
    description = _recorded_description_with_line_separator()
    payload = {
        "type": "tool-output-available",
        "toolCallId": "call-1",
        "output": {"studies": [{"description": description}]},
    }

    chunks = parse_sse_body(_wire(payload, 1))

    assert len(chunks) == 1
    assert chunks[0] == payload
    assert chunks[0]["output"]["studies"][0]["description"] == description


def test_frames_around_a_u2028_payload_keep_their_order() -> None:
    description = _recorded_description_with_line_separator()
    body = (
        _wire({"type": "start"}, 1)
        + _wire({"type": "tool-output-available", "output": description}, 2)
        + _wire({"type": "finish"}, 3)
        + "id: 4\ndata: [DONE]\n\n"
    )

    chunks = parse_sse_body(body)

    assert [chunk["type"] for chunk in chunks] == [
        "start",
        "tool-output-available",
        "finish",
        "done",
    ]
    assert chunks[1]["output"] == description


def test_crlf_delimited_frames_parse() -> None:
    body = 'id: 1\r\ndata: {"type": "start"}\r\n\r\nid: 2\r\ndata: [DONE]\r\n\r\n'

    chunks = parse_sse_body(body)

    assert chunks == [{"type": "start"}, {"type": "done"}]
