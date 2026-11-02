from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from decimal import Decimal

import httpx
from assistant_core.cost import cost_for_run
from assistant_core.platform.types import PaidBy
from openai import APIError, APIStatusError
from pydantic_ai.usage import RunUsage
from veupathdb_mcp.catalog import (
    DecisionRequest,
    DecisionResponse,
    DecisionUsage,
    use_decisions_transport,
)

from pathfinder.platform.model_keys import is_mock_deployment, keyed_provider

DECISIONS_MODEL = "openai:gpt-6-luna"

type DecisionsSpendSink = Callable[[int, Decimal, PaidBy], None]

_sink: ContextVar[DecisionsSpendSink | None] = ContextVar(
    "decisions_spend_sink", default=None
)


@contextmanager
def decisions_spend_to(sink: DecisionsSpendSink) -> Iterator[None]:
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


def decision_cost(usage: DecisionUsage) -> Decimal:
    provider_name, model_name = DECISIONS_MODEL.split(":", 1)
    return cost_for_run(
        usage=RunUsage(
            input_tokens=usage.input_tokens,
            cache_read_tokens=usage.cached_tokens,
            cache_write_tokens=usage.cache_write_tokens,
        ),
        model_name=model_name,
        provider_name=provider_name,
        provider_url=None,
    )


class DecisionsRefusedError(httpx.HTTPError):
    def __init__(self, status: int) -> None:
        super().__init__(f"Decisions answered {status}")


class DecisionsUnansweredError(httpx.HTTPError):
    def __init__(self) -> None:
        super().__init__("Decisions did not answer")


async def send_decision(request: DecisionRequest) -> DecisionResponse:
    provider, paid_by = keyed_provider(DECISIONS_MODEL)
    try:
        raw = await provider.client.post(
            "/decisions", cast_to=httpx.Response, body=request.model_dump(mode="json")
        )
    except APIStatusError as refused:
        raise DecisionsRefusedError(refused.status_code) from None
    except APIError:
        raise DecisionsUnansweredError from None
    response = DecisionResponse.model_validate_json(raw.content)
    sink = _sink.get()
    if sink is not None:
        sink(response.usage.input_tokens, decision_cost(response.usage), paid_by)
    return response


async def _no_decision(request: DecisionRequest) -> DecisionResponse | None:
    del request
    return None


def install_decisions_transport() -> None:
    use_decisions_transport(_no_decision if is_mock_deployment() else send_decision)


__all__ = [
    "DECISIONS_MODEL",
    "decision_cost",
    "decisions_spend_to",
    "install_decisions_transport",
    "send_decision",
]
