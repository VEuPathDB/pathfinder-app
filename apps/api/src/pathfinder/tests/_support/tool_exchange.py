"""One tool call and its return, as the two messages a model history holds."""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)


def tool_exchange(
    index: int,
    tool_name: str,
    content: object,
    args: dict[str, Any] | None = None,
) -> list[ModelMessage]:
    call_id = f"call_{index}"
    return [
        ModelResponse(
            parts=[
                ToolCallPart(tool_name=tool_name, args=args or {}, tool_call_id=call_id)
            ]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name=tool_name, content=content, tool_call_id=call_id
                )
            ]
        ),
    ]
