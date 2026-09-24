"""The refusals each model provider answers a key it does not accept.

Every fixture is the ``ModelHTTPError`` pydantic-ai raised for one generation
request made with a made-up key, through the construction a turn uses. The
refusal classifier reads these bodies and nothing written by hand. A made-up
key costs nothing, so recording needs no credential.

Usage::

    python -m pathfinder.devtools.provider_refusals record
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import sys
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, JsonValue, SecretStr
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models import infer_model

from pathfinder.ai.models.catalog import get_smallest_model
from pathfinder.domain.provider_keys import KEYABLE_PROVIDERS, KeyableProvider
from pathfinder.platform.model_keys import build_provider, one_generation

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "refusals"

# Shaped like each provider's keys, so the provider reads it as a key and
# refuses it. The last four characters are the ones a refusal may echo.
MADE_UP_KEYS: Mapping[KeyableProvider, str] = {
    "openai": "sk-proj-" + "0" * 40 + "WXYZ",
    "anthropic": "sk-ant-api03-" + "0" * 40 + "WXYZ",
    "google": "AIza" + "0" * 31 + "WXYZ",
}


class RecordedRefusal(BaseModel):
    """What one provider answered, as the classifier receives it."""

    model_config = ConfigDict(frozen=True)

    provider: KeyableProvider
    model: str
    status: int
    body: JsonValue
    recorded_at: datetime.datetime


def fixture_path(provider: KeyableProvider) -> Path:
    return FIXTURE_DIR / f"{provider}-invalid-key.json"


def load_recorded(provider: KeyableProvider) -> RecordedRefusal:
    return RecordedRefusal.model_validate_json(fixture_path(provider).read_text())


async def _record(provider: KeyableProvider) -> RecordedRefusal:
    model_id = get_smallest_model(provider).id
    key = SecretStr(MADE_UP_KEYS[provider])
    model = infer_model(
        model_id, provider_factory=lambda _: build_provider(provider, key)
    )
    try:
        await one_generation(model)
    except ModelHTTPError as exc:
        return RecordedRefusal.model_validate(
            {
                "provider": provider,
                "model": model_id,
                "status": exc.status_code,
                "body": exc.body,
                "recorded_at": datetime.datetime.now(datetime.UTC),
            }
        )
    msg = f"{provider} accepted a made-up key; nothing to record"
    raise RuntimeError(msg)


async def record() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    for provider in KEYABLE_PROVIDERS:
        recorded = await _record(provider)
        fixture_path(provider).write_text(recorded.model_dump_json(indent=2) + "\n")
        sys.stdout.write(f"{provider}: {recorded.status}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m pathfinder.devtools.provider_refusals"
    )
    parser.add_argument("command", choices=["record"])
    parser.parse_args()
    asyncio.run(record())


if __name__ == "__main__":
    main()
