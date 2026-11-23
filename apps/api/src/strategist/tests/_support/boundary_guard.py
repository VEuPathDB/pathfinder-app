from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest
from pydantic_ai._instrumentation import get_instructions
from pydantic_ai._run_context import get_current_run_context
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelRequestPart,
    ModelResponse,
    RetryFeedbackPart,
    SystemPromptPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from strategist.tests._support.tool_names import (
    RETIRED_TOOLS,
    all_tool_names,
    allowed_in,
    named_tools,
)


def _part_text(part: ModelRequestPart) -> tuple[str, str] | None:
    match part:
        case SystemPromptPart(content=content):
            return "system prompt", content
        case UserPromptPart(content=str() as content):
            return "user prompt", content
        case UserPromptPart(content=content):
            return "user prompt", " ".join(c for c in content if isinstance(c, str))
        case ToolReturnPart(outcome=outcome, tool_name=tool_name):
            kind = "retry" if outcome == "retried" else "tool return"
            return f"{kind} of {tool_name}", part.model_response_str()
        case RetryFeedbackPart():
            return "retry feedback", part.model_response()
        case _:
            return None


def _since_last_response(messages: list[ModelMessage]) -> Iterator[tuple[str, str]]:
    fresh: list[ModelRequest] = []
    for message in reversed(messages):
        if isinstance(message, ModelResponse):
            break
        fresh.append(message)
    for request in reversed(fresh):
        for part in request.parts:
            text = _part_text(part)
            if text is not None:
                yield text


def _descriptions(parameters: ModelRequestParameters) -> Iterator[tuple[str, str]]:
    for tool in parameters.function_tools:
        yield f"description of {tool.name}", tool.description or ""
        yield f"schema of {tool.name}", json.dumps(tool.parameters_json_schema)


def _role() -> str | None:
    run = get_current_run_context()
    return None if run is None or run.agent is None else run.agent.name


def foreign_in_request(
    messages: list[ModelMessage],
    parameters: ModelRequestParameters,
    role: str | None,
) -> list[str]:
    offered = {tool.name for tool in parameters.function_tools}
    texts = [("instructions", get_instructions(messages, parameters) or "")]
    texts.extend(_descriptions(parameters))
    texts.extend(_since_last_response(messages))
    found: list[str] = []
    for kind, text in texts:
        named = named_tools(text)
        unheld = named - offered - allowed_in(text, role)
        foreign = sorted(unheld | (named & RETIRED_TOOLS))
        if foreign:
            found.append(f"{kind} names {foreign}")
    return found


def _refuse(
    refused: list[str],
    messages: list[ModelMessage],
    parameters: ModelRequestParameters,
) -> None:
    found = foreign_in_request(messages, parameters, _role())
    if found:
        message = f"A model request names tools it does not offer: {found}"
        refused.append(message)
        raise AssertionError(message)


def _guarded_request(
    refused: list[str], original: Callable[..., Any]
) -> Callable[..., Any]:
    async def request(
        self: Any,
        messages: list[ModelMessage],
        model_settings: Any,
        model_request_parameters: ModelRequestParameters,
        *args: Any,
        **kwargs: Any,
    ) -> ModelResponse:
        _refuse(refused, messages, model_request_parameters)
        response: ModelResponse = await original(
            self, messages, model_settings, model_request_parameters, *args, **kwargs
        )
        return response

    return request


def _guarded_stream(
    refused: list[str], original: Callable[..., Any]
) -> Callable[..., Any]:
    @contextlib.asynccontextmanager
    async def request_stream(
        self: Any,
        messages: list[ModelMessage],
        model_settings: Any,
        model_request_parameters: ModelRequestParameters,
        *args: Any,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        _refuse(refused, messages, model_request_parameters)
        async with original(
            self, messages, model_settings, model_request_parameters, *args, **kwargs
        ) as streamed:
            yield streamed

    return request_stream


def guard_the_model_boundary(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    all_tool_names()
    refused: list[str] = []
    for model in (FunctionModel, TestModel):
        monkeypatch.setattr(model, "request", _guarded_request(refused, model.request))
        monkeypatch.setattr(
            model, "request_stream", _guarded_stream(refused, model.request_stream)
        )
    return refused
