"""The thread title and the notes compaction each write a usage row for their payer.

The title runs on the deployment's key when the researcher holds none, and the
compaction on the researcher's key when theirs pays for its provider. A refused
compaction keeps the notes and is still charged. Only the model is a double.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import httpx2
import pytest
from assistant_core import quota
from assistant_core.persistence.models import Conversation
from assistant_core.platform import db
from assistant_core.platform.types import PaidBy
from assistant_core.scratchpad.compactor import COMPACT_COUNT_THRESHOLD
from assistant_core.scratchpad.models import NoteCreate
from assistant_core.scratchpad.notebook import ScratchpadNotebook
from langgraph.runtime import Runtime
from openai.types.responses import Response
from pydantic import SecretStr
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.providers import Provider
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import RequestUsage

from pathfinder.ai.conversation.title_generator import charged_conversation_title
from pathfinder.ai.graph import nodes
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.domain.provider_keys import KeyableProvider, ProviderKeyring
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.persistence.models import User
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.model_keys import ProviderBuilder, attach_keyring
from pathfinder.tests._support.provider_wire import allow_requests_to_the_wire

pytestmark = pytest.mark.asyncio

_TITLE_INPUT_TOKENS = 42
_TITLE_OUTPUT_TOKENS = 6
_COMPACTION_INPUT_TOKENS = 900
_COMPACTION_OUTPUT_TOKENS = 40
_TURN_TOKENS = 1000


async def _seed_thread() -> tuple[UUID, UUID]:
    conversation_id, user_id = uuid4(), uuid4()
    async with db.async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="metered",
            )
        )
        await session.commit()
    return conversation_id, user_id


async def _spent(user_id: UUID, paid_by: PaidBy) -> quota.UsageTotals:
    async with db.async_session_factory() as session:
        return await quota.get_period_totals(session, user_id, paid_by=paid_by)


def _title_model() -> Model:
    def answer(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        return ModelResponse(
            parts=[TextPart("Plasmodium Kinase Survey")],
            usage=RequestUsage(
                input_tokens=_TITLE_INPUT_TOKENS, output_tokens=_TITLE_OUTPUT_TOKENS
            ),
        )

    return FunctionModel(answer)


async def test_a_title_writes_its_usage_on_the_deployments_row(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    monkeypatch.setattr(get_settings(), "pathfinder_chat_provider", "mock")
    _, user_id = await _seed_thread()

    title = await charged_conversation_title(
        "list the kinases of P. falciparum", _title_model, user_id=user_id
    )

    assert title == "Plasmodium Kinase Survey"
    deployment = await _spent(user_id, PaidBy.DEPLOYMENT)
    assert deployment.tokens == _TITLE_INPUT_TOKENS + _TITLE_OUTPUT_TOKENS
    assert (await _spent(user_id, PaidBy.USER)).tokens == 0


def _compaction_answer(model: str, body: str) -> dict[str, Any]:
    """One finished Responses answer that calls the compactor's output tool."""
    notes = {"notes": [{"title": "kinases", "summary": "merged", "body": body}]}
    return Response.model_validate(
        {
            "id": "resp_compaction",
            "created_at": 1_790_000_000,
            "model": model,
            "object": "response",
            "status": "completed",
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "output": [
                {
                    "id": "fc_compaction",
                    "type": "function_call",
                    "call_id": "call_compaction",
                    "name": "final_result",
                    "arguments": json.dumps(notes),
                    "status": "completed",
                }
            ],
            "usage": {
                "input_tokens": _COMPACTION_INPUT_TOKENS,
                "output_tokens": _COMPACTION_OUTPUT_TOKENS,
                "total_tokens": _COMPACTION_INPUT_TOKENS + _COMPACTION_OUTPUT_TOKENS,
                "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }
    ).model_dump(mode="json", exclude_none=True)


def _answering(body: str) -> ProviderBuilder:
    def build(name: KeyableProvider, key: SecretStr) -> Provider[Any]:
        assert name == "openai"

        def answer(request: httpx2.Request) -> httpx2.Response:
            model = json.loads(request.content)["model"]
            return httpx2.Response(200, json=_compaction_answer(model, body))

        client = httpx2.AsyncClient(transport=httpx2.MockTransport(answer))
        return OpenAIProvider(api_key=key.get_secret_value(), http_client=client)

    return build


async def _fill_the_notebook(conversation_id: UUID, body: str = "a finding") -> None:
    notebook = ScratchpadNotebook(db.async_session_factory, conversation_id)
    for index in range(COMPACT_COUNT_THRESHOLD + 1):
        await notebook.create(
            NoteCreate(title=f"note {index}", summary="a finding", body=body)
        )


def _checked_turn(conversation_id: UUID, user_id: UUID) -> PipelineState:
    state = PipelineState(
        conversation_id=conversation_id,
        user_id=user_id,
        site_id="plasmodb",
        mode="strategy",
        turn_total_tokens=_TURN_TOKENS,
        turn_total_cost_usd=Decimal("0.01"),
        domain=StrategyDomainState(
            verification_digest=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="ok",
                reason="verified",
                success=True,
            )
        ),
    )
    state.turn_markers.verified = True
    state.turn_markers.verification_dispatched = True
    return state


def _runtime(user_id: UUID, chunks: list[Any]) -> Runtime[Context]:
    return Runtime(
        context=Context(
            site_id="plasmodb",
            user_id=user_id,
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=db.async_session_factory,
            cancel_event=asyncio.Event(),
        ),
        stream_writer=chunks.append,
    )


def _on_the_researchers_key(monkeypatch: pytest.MonkeyPatch) -> ProviderKeyring:
    allow_requests_to_the_wire(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "pathfinder_chat_provider", "default")
    monkeypatch.setattr(settings, "default_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-deployment-sentinel-0000")
    return ProviderKeyring(active={"openai": SecretStr("sk-user-sentinel-1111")})


def _usage_totals(chunks: list[Any]) -> list[int]:
    return [
        c["chunk"]["data"]["totalTokens"]
        for c in chunks
        if c["chunk"]["type"] == "data-turn-usage"
    ]


async def test_a_compaction_on_the_researchers_key_writes_their_row(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    keyring = _on_the_researchers_key(monkeypatch)
    conversation_id, user_id = await _seed_thread()
    await _fill_the_notebook(conversation_id)
    chunks: list[Any] = []

    with attach_keyring(keyring, build=_answering("merged")):
        command = await nodes.finalize_turn_node(
            _checked_turn(conversation_id, user_id), _runtime(user_id, chunks)
        )

    compaction_tokens = _COMPACTION_INPUT_TOKENS + _COMPACTION_OUTPUT_TOKENS
    researcher = await _spent(user_id, PaidBy.USER)
    assert researcher.tokens == compaction_tokens
    assert researcher.cost_usd > 0
    assert (await _spent(user_id, PaidBy.DEPLOYMENT)).tokens == 0
    assert _usage_totals(chunks) == [_TURN_TOKENS + compaction_tokens]
    assert [c["chunk"]["type"] for c in chunks] == [
        "data-scratchpad-updated",
        "data-turn-usage",
    ]
    assert command.update == {
        "turn_total_tokens": _TURN_TOKENS + compaction_tokens,
        "turn_total_cost_usd": Decimal("0.01") + researcher.cost_usd,
    }


async def test_a_compaction_that_drops_a_gene_id_keeps_the_notes_and_is_charged(
    patch_app_db_engine: None,
    db_cleaner: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine, db_cleaner
    keyring = _on_the_researchers_key(monkeypatch)
    conversation_id, user_id = await _seed_thread()
    await _fill_the_notebook(conversation_id, body="PF3D7_0102300 is a kinase")
    chunks: list[Any] = []

    with attach_keyring(keyring, build=_answering("a kinase")):
        await nodes.finalize_turn_node(
            _checked_turn(conversation_id, user_id), _runtime(user_id, chunks)
        )

    notebook = ScratchpadNotebook(db.async_session_factory, conversation_id)
    totals = await notebook.compaction_totals()
    assert totals.compactable_count == COMPACT_COUNT_THRESHOLD + 1
    three_attempts = 3 * (_COMPACTION_INPUT_TOKENS + _COMPACTION_OUTPUT_TOKENS)
    assert (await _spent(user_id, PaidBy.USER)).tokens == three_attempts
    assert _usage_totals(chunks) == [_TURN_TOKENS + three_attempts]
    assert [c["chunk"]["type"] for c in chunks] == ["data-turn-usage"]
