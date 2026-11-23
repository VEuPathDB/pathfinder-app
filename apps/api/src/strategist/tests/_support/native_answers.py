from __future__ import annotations

import json
from collections.abc import Mapping

from pydantic_ai.messages import ModelMessage, ModelRequest, TextPart, UserPromptPart

_FEEDBACK = "failed the application's validation"


def answered(output: Mapping[str, object]) -> TextPart:
    return TextPart(json.dumps(dict(output)))


def feedback(messages: list[ModelMessage]) -> list[str]:
    return [
        str(part.content)
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, UserPromptPart) and _FEEDBACK in str(part.content)
    ]
