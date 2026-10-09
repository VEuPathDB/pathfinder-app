from __future__ import annotations

from typing import Any

import pytest
from assistant_core.conversation.vercel_adapter import PhaseStreamEmitter
from pydantic import SecretStr
from pydantic_ai.models import Model, infer_model

from pathfinder.assistants.site_help import agent
from pathfinder.assistants.site_help.agent import SiteHelpDeps, build_site_help_agent
from pathfinder.tests._support.models import ANTHROPIC_STANDARD
from pathfinder.tests._support.provider_wire import (
    ProviderWire,
    allow_requests_to_the_wire,
)


async def test_a_declined_site_help_turn_withdraws_its_prompt_in_plain_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire = ProviderWire(declines=True)
    model: Model = infer_model(
        ANTHROPIC_STANDARD,
        provider_factory=lambda _: wire.build("anthropic", SecretStr("sk-ant-test")),
    )
    allow_requests_to_the_wire(monkeypatch)
    monkeypatch.setattr(agent, "turn_model", lambda: (model, None))
    emitter = PhaseStreamEmitter(message_id="m1", prompt_message_id="u1")

    async with build_site_help_agent().run_stream_events(
        "Which site holds the anthrax toxin genes?",
        deps=SiteHelpDeps(site_id="plasmodb"),
    ) as events:
        written: list[dict[str, Any]] = [
            chunk.model_dump(by_alias=True, mode="json", exclude_none=True)
            async for chunk in emitter.chunks(events)
        ]
    chunks = [c for c in written if c["type"] in {"error", "data-turn-withdrawn"}]

    worded = chunks[1]["errorText"]
    assert worded.startswith("Claude Sonnet 5.5 declined this request.")
    assert chunks == [
        {
            "type": "data-turn-withdrawn",
            "data": {"errorText": worded, "messageId": "u1"},
        },
        {"type": "error", "errorText": worded},
    ]
    assert len(wire.requests) == 1
