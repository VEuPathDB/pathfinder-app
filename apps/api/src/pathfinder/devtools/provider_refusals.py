"""The refusals each model provider answers a key it does not accept.

A recorded fixture is the ``ModelHTTPError`` pydantic-ai raised for one
generation request, through the construction a turn uses. A documented fixture
is a body copied from the provider's error reference, for an account state no
key here is in; it names the page it was read from. The refusal classifier
reads these bodies and nothing else.

Usage::

    python -m pathfinder.devtools.provider_refusals record
    python -m pathfinder.devtools.provider_refusals record anthropic-no-credit
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, JsonValue, SecretStr, model_validator
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models import infer_model

from pathfinder.ai.models.catalog import get_smallest_model
from pathfinder.domain.provider_keys import KeyableProvider, KeyRefusal
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_keys import build_provider, one_generation

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "refusals"

type Provenance = Literal["recorded", "documented"]

# Shaped like each provider's keys, so the provider reads it as a key and
# refuses it. The last four characters are the ones a refusal may echo.
MADE_UP_KEYS: Mapping[KeyableProvider, str] = {
    "openai": "sk-proj-" + "0" * 40 + "WXYZ",
    "anthropic": "sk-ant-api03-" + "0" * 40 + "WXYZ",
    "google": "AIza" + "0" * 31 + "WXYZ",
}


class ProviderRefusal(BaseModel):
    """What one provider answers a refused key, and where the body comes from."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: KeyableProvider
    refusal: KeyRefusal
    status: int
    body: JsonValue
    provenance: Provenance
    # The key a recorded body answered, or the page a documented body is from.
    source: str
    model: str | None = None
    read_at: datetime.datetime

    @model_validator(mode="after")
    def _a_documented_body_cites_its_page(self) -> Self:
        if self.provenance == "documented" and not self.source.startswith("https://"):
            msg = "a documented refusal cites the https page it was read from"
            raise ValueError(msg)
        if self.provenance == "recorded" and self.model is None:
            msg = "a recorded refusal names the model its request named"
            raise ValueError(msg)
        return self


def fixture_path(name: str) -> Path:
    return FIXTURE_DIR / f"{name}.json"


def load_refusal(name: str) -> ProviderRefusal:
    return ProviderRefusal.model_validate_json(fixture_path(name).read_text())


def every_refusal() -> dict[str, ProviderRefusal]:
    """Every fixture, by its name."""
    return {
        path.stem: ProviderRefusal.model_validate_json(path.read_text())
        for path in sorted(FIXTURE_DIR.glob("*.json"))
    }


def _made_up(provider: KeyableProvider) -> Callable[[], SecretStr]:
    return lambda: SecretStr(MADE_UP_KEYS[provider])


def _deployment_key(provider: KeyableProvider) -> SecretStr:
    key = get_settings().deployment_credential(provider)
    if not key.strip():
        msg = f"the deployment holds no {provider} key to record with"
        raise RuntimeError(msg)
    return SecretStr(key)


@dataclass(frozen=True)
class _Case:
    """One refusal a key in a known state receives."""

    provider: KeyableProvider
    refusal: KeyRefusal
    source: str
    key: Callable[[], SecretStr]


CASES: Mapping[str, _Case] = {
    "openai-invalid-key": _Case(
        "openai", KeyRefusal.INVALID, "a made-up key", _made_up("openai")
    ),
    "anthropic-invalid-key": _Case(
        "anthropic", KeyRefusal.INVALID, "a made-up key", _made_up("anthropic")
    ),
    "google-invalid-key": _Case(
        "google", KeyRefusal.INVALID, "a made-up key", _made_up("google")
    ),
    "anthropic-no-credit": _Case(
        "anthropic",
        KeyRefusal.NO_CREDIT,
        "the deployment's Anthropic key, on an account with no credit",
        lambda: _deployment_key("anthropic"),
    ),
}

_MADE_UP_CASES = [
    name for name, case in CASES.items() if case.source == "a made-up key"
]


async def _record(case: _Case) -> ProviderRefusal:
    model_id = get_smallest_model(case.provider).id
    key = case.key()
    model = infer_model(
        model_id, provider_factory=lambda _: build_provider(case.provider, key)
    )
    try:
        await one_generation(model)
    except ModelHTTPError as exc:
        return ProviderRefusal.model_validate(
            {
                "provider": case.provider,
                "refusal": case.refusal,
                "status": exc.status_code,
                "body": exc.body,
                "provenance": "recorded",
                "source": case.source,
                "model": model_id,
                "read_at": datetime.datetime.now(datetime.UTC),
            }
        )
    msg = f"{case.provider} accepted {case.source}; nothing to record"
    raise RuntimeError(msg)


async def record(names: list[str]) -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        recorded = await _record(CASES[name])
        fixture_path(name).write_text(recorded.model_dump_json(indent=2) + "\n")
        sys.stdout.write(f"{name}: {recorded.status}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m pathfinder.devtools.provider_refusals"
    )
    parser.add_argument("command", choices=["record"])
    parser.add_argument(
        "cases",
        nargs="*",
        choices=sorted(CASES),
        help="the cases to record; the made-up key cases when none is named",
    )
    args = parser.parse_args()
    asyncio.run(record(args.cases or _MADE_UP_CASES))


if __name__ == "__main__":
    main()
