from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx2
import pytest
from assistant_core.cost import cost_for_run
from assistant_core.platform.types import PaidBy
from openai import AsyncOpenAI
from pydantic import SecretStr
from pydantic_ai.providers import Provider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RunUsage
from structlog.testing import capture_logs
from veupathdb_mcp.catalog import (
    DecisionRequest,
    DecisionUsage,
    decide,
    post_decision,
    use_decisions_transport,
)

from pathfinder.ai.capabilities.decisions_spend import (
    decision_cost,
    decisions_spend_to,
    install_decisions_transport,
    send_decision,
)
from pathfinder.domain.provider_keys import KeyableProvider, ProviderKeyring
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_catalog import install_catalog_prices
from pathfinder.platform.model_keys import attach_keyring

FIXTURE = Path(__file__).parents[3] / "fixtures" / "decisions" / "interpro_pick.json"
RECORDED = json.loads(FIXTURE.read_text())
RESEARCHER_KEY = "sk-researcher-test-key"
DEPLOYMENT_KEY = "sk-deployment-test-key"


class _Wire:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict[str, object]]] = []

    def answer(self, request: httpx2.Request) -> httpx2.Response:
        self.sent.append(
            (
                str(request.url),
                request.headers["authorization"],
                json.loads(request.content),
            )
        )
        return httpx2.Response(200, json=RECORDED["response"])

    def build(self, name: KeyableProvider, key: SecretStr) -> Provider[Any]:
        assert name == "openai"
        client = AsyncOpenAI(
            api_key=key.get_secret_value(),
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(self.answer)),
            max_retries=0,
        )
        return OpenAIProvider(openai_client=client)


@pytest.fixture(autouse=True)
def _prices(monkeypatch: pytest.MonkeyPatch) -> None:
    install_catalog_prices()
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    monkeypatch.setattr(settings, "openai_api_key", DEPLOYMENT_KEY)


def _request() -> DecisionRequest:
    return DecisionRequest.model_validate(RECORDED["request"])


def test_a_decision_is_priced_as_gpt_6_luna_input() -> None:
    usage = DecisionUsage(input_tokens=1000, cached_tokens=600, cache_write_tokens=100)

    assert decision_cost(usage) == cost_for_run(
        usage=RunUsage(
            input_tokens=1000, cache_read_tokens=600, cache_write_tokens=100
        ),
        model_name="gpt-6-luna",
        provider_name="openai",
        provider_url=None,
    )
    assert decision_cost(DecisionUsage(input_tokens=1000)) == Decimal("0.0001")


async def test_a_decision_in_a_turn_is_sent_on_the_researchers_key_and_charged_to_them() -> (
    None
):
    wire = _Wire()
    spent: list[tuple[int, Decimal, PaidBy]] = []
    keyring = ProviderKeyring(active={"openai": SecretStr(RESEARCHER_KEY)})

    with (
        attach_keyring(keyring, build=wire.build),
        decisions_spend_to(lambda t, c, p: spent.append((t, c, p))),
    ):
        answered = await send_decision(_request())

    [(url, auth, body)] = wire.sent
    assert (url, auth) == (
        "https://api.openai.com/v1/decisions",
        f"Bearer {RESEARCHER_KEY}",
    )
    assert body == _request().model_dump(mode="json")
    assert answered.usage.input_tokens == 711
    assert spent == [(711, decision_cost(DecisionUsage(input_tokens=711)), PaidBy.USER)]


async def test_a_decision_with_no_researcher_key_is_sent_on_the_deployments_key() -> (
    None
):
    wire = _Wire()
    spent: list[tuple[int, Decimal, PaidBy]] = []

    with (
        attach_keyring(ProviderKeyring(), build=wire.build),
        decisions_spend_to(lambda t, c, p: spent.append((t, c, p))),
    ):
        await send_decision(_request())

    assert [auth for _, auth, _ in wire.sent] == [f"Bearer {DEPLOYMENT_KEY}"]
    assert [p for _, _, p in spent] == [PaidBy.DEPLOYMENT]


async def test_a_decision_outside_a_turn_is_sent_and_charged_to_no_one() -> None:
    wire = _Wire()

    with attach_keyring(ProviderKeyring(), build=wire.build):
        answered = await send_decision(_request())

    assert (len(wire.sent), answered.usage.input_tokens) == (1, 711)


class _RefusingWire(_Wire):
    def answer(self, request: httpx2.Request) -> httpx2.Response:
        self.sent.append((str(request.url), request.headers["authorization"], {}))
        return httpx2.Response(
            401,
            json={
                "error": {"message": f"Incorrect API key provided: {RESEARCHER_KEY}"}
            },
        )


async def test_a_refused_decision_leaves_the_catalog_its_own_result() -> None:
    wire = _RefusingWire()
    use_decisions_transport(send_decision)
    try:
        with (
            attach_keyring(ProviderKeyring(), build=wire.build),
            capture_logs() as logged,
        ):
            answered = await decide(_request(), purpose="search candidates")
    finally:
        use_decisions_transport(post_decision)

    assert (answered, len(wire.sent)) == (None, 1)
    assert RESEARCHER_KEY not in json.dumps(logged, default=str)
    assert [entry.get("error") for entry in logged] == ["Decisions answered 401"]


async def test_a_mock_deployment_asks_no_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "pathfinder_chat_provider", "mock")
    wire = _Wire()
    install_decisions_transport()
    try:
        with attach_keyring(ProviderKeyring(), build=wire.build):
            answered = await decide(_request(), purpose="search candidates")
    finally:
        use_decisions_transport(post_decision)

    assert (answered, wire.sent) == (None, [])


async def test_a_live_deployment_sends_each_decision_on_the_turns_key() -> None:
    wire = _Wire()
    install_decisions_transport()
    try:
        with attach_keyring(ProviderKeyring(), build=wire.build):
            answered = await decide(_request(), purpose="search candidates")
    finally:
        use_decisions_transport(post_decision)

    assert (answered is not None, [auth for _, auth, _ in wire.sent]) == (
        True,
        [f"Bearer {DEPLOYMENT_KEY}"],
    )
