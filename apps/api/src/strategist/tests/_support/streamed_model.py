"""A scripted FunctionModel that answers a streamed request with the same response."""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable

from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.profiles import ModelProfile

type Respond = Callable[
    [list[ModelMessage], AgentInfo], ModelResponse | Awaitable[ModelResponse]
]


def streamed(
    respond: Respond,
    *,
    model_name: str | None = None,
    profile: ModelProfile | None = None,
) -> FunctionModel:
    async def _stream(
        messages: list[ModelMessage], info: AgentInfo
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        response = respond(messages, info)
        if inspect.isawaitable(response):
            response = await response
        calls: dict[int, DeltaToolCall] = {}
        for part in response.parts:
            match part:
                case TextPart(content=text) if text:
                    yield text
                case ToolCallPart():
                    calls[len(calls)] = DeltaToolCall(
                        name=part.tool_name,
                        json_args=part.args_as_json_str(),
                        tool_call_id=part.tool_call_id,
                    )
                case _:
                    pass
        if calls:
            yield calls

    return FunctionModel(
        respond, stream_function=_stream, model_name=model_name, profile=profile
    )
