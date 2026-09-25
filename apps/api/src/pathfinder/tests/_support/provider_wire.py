"""Real provider clients whose http client answers from recorded bodies.

The model provider is the one boundary a test replaces: every request still
goes through the provider SDK, and the transport records what it was sent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx2
import pytest
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseCreatedEvent,
    ResponseTextDeltaEvent,
)
from pydantic import BaseModel, ConfigDict, JsonValue, SecretStr
from pydantic_ai import models
from pydantic_ai.providers import Provider
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from pathfinder.devtools.provider_refusals import ProviderRefusal, load_refusal
from pathfinder.domain.provider_keys import KeyableProvider

ANSWER_TEXT = "Plasmodium kinases answered."


class _Requested(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    stream: bool = False


def allow_requests_to_the_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let a model send requests; the wire answers them without a network."""
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", True)


def refusal_on_the_wire(refusal: ProviderRefusal) -> JsonValue:
    """The refusal as the provider sends it.

    pydantic-ai hands over the ``error`` object of an OpenAI answer and the
    whole body of the other two.
    """
    return {"error": refusal.body} if refusal.provider == "openai" else refusal.body


def _openai_response(model: str) -> Response:
    return Response.model_validate(
        {
            "id": "resp_test",
            "created_at": 1_790_000_000,
            "model": model,
            "object": "response",
            "status": "completed",
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {"type": "output_text", "text": ANSWER_TEXT, "annotations": []}
                    ],
                }
            ],
            "usage": {
                "input_tokens": 12,
                "output_tokens": 5,
                "total_tokens": 17,
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
    )


def openai_answer(model: str) -> JsonValue:
    """One finished OpenAI Responses answer, shaped by the SDK's own model."""
    dumped: JsonValue = _openai_response(model).model_dump(
        mode="json", exclude_none=True
    )
    return dumped


def openai_stream(model: str) -> bytes:
    """The same answer as the server-sent events a streamed request receives."""
    finished = _openai_response(model)
    started = finished.model_copy(update={"status": "in_progress", "output": []})
    events: list[
        ResponseCreatedEvent | ResponseTextDeltaEvent | ResponseCompletedEvent
    ] = [
        ResponseCreatedEvent(
            type="response.created", response=started, sequence_number=0
        ),
        ResponseTextDeltaEvent(
            type="response.output_text.delta",
            item_id="msg_test",
            output_index=0,
            content_index=0,
            delta=ANSWER_TEXT,
            logprobs=[],
            sequence_number=1,
        ),
        ResponseCompletedEvent(
            type="response.completed", response=finished, sequence_number=2
        ),
    ]
    frames = (
        f"event: {event.type}\ndata: "
        f"{json.dumps(event.model_dump(mode='json', exclude_none=True))}\n\n"
        for event in events
    )
    return "".join(frames).encode()


@dataclass
class ProviderWire:
    """Builds real providers on a transport that records every request.

    ``refuse`` answers each request with the provider's ``refused_by`` fixture
    and ``status`` with that status and no body; otherwise an OpenAI request
    gets a finished answer.
    """

    refuse: bool = False
    refused_by: str = "invalid-key"
    status: int | None = None
    requests: list[httpx2.Request] = field(default_factory=list)

    def _answer(
        self, provider: KeyableProvider, request: httpx2.Request
    ) -> httpx2.Response:
        self.requests.append(request)
        if self.refuse:
            refusal = load_refusal(f"{provider}-{self.refused_by}")
            return httpx2.Response(refusal.status, json=refusal_on_the_wire(refusal))
        if self.status is not None:
            return httpx2.Response(self.status)
        requested = _Requested.model_validate_json(request.content)
        if requested.stream:
            return httpx2.Response(
                200,
                content=openai_stream(requested.model),
                headers={"content-type": "text/event-stream"},
            )
        return httpx2.Response(200, json=openai_answer(requested.model))

    def build(self, name: KeyableProvider, key: SecretStr) -> Provider[Any]:
        client = httpx2.AsyncClient(
            transport=httpx2.MockTransport(lambda request: self._answer(name, request))
        )
        secret = key.get_secret_value()
        match name:
            case "openai":
                return OpenAIProvider(api_key=secret, http_client=client)
            case "anthropic":
                return AnthropicProvider(api_key=secret, http_client=client)
            case "google":
                return GoogleProvider(api_key=secret, http_client=client)

    def sent_headers(self) -> list[dict[str, str]]:
        return [dict(request.headers) for request in self.requests]
