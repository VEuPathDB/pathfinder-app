from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx2
from openai import AsyncOpenAI
from pydantic import SecretStr
from pydantic_ai.providers import Provider
from pydantic_ai.providers.openai import OpenAIProvider

from pathfinder.domain.provider_keys import KeyableProvider

DECISIONS_FIXTURES = Path(__file__).parents[1] / "fixtures" / "decisions"


def recorded_decision(name: str) -> dict[str, Any]:
    recorded: dict[str, Any] = json.loads((DECISIONS_FIXTURES / name).read_text())
    return recorded


class DecisionsWire:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.sent: list[tuple[str, str, dict[str, object]]] = []

    def answer(self, request: httpx2.Request) -> httpx2.Response:
        self.sent.append(
            (
                str(request.url),
                request.headers["authorization"],
                json.loads(request.content),
            )
        )
        return httpx2.Response(200, json=self.response)

    def build(self, name: KeyableProvider, key: SecretStr) -> Provider[Any]:
        assert name == "openai"
        client = AsyncOpenAI(
            api_key=key.get_secret_value(),
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self.answer)),
            max_retries=0,
        )
        return OpenAIProvider(openai_client=client)
