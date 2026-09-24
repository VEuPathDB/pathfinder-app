"""Both turn kinds a worker runs read the researcher's keys and mark what was refused."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.turn_state import DurableTaskResult
from assistant_core.platform.context import PhaseOverrides
from assistant_core.platform.types import PaidBy
from assistant_core.tasks.completion_turn import CompletionTurn
from pydantic import SecretStr
from pydantic_ai.models import Model
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.domain.provider_keys import KeyRefusal, KeyStatuses
from pathfinder.jobs.completion import open_completion_turn
from pathfinder.jobs.turn_keys import turn_keys
from pathfinder.platform.config import get_settings
from pathfinder.platform.errors import ProviderKeyRefusedError
from pathfinder.platform.model_keys import keyed_model, one_generation, turn_paid_by
from pathfinder.services.provider_keys import key_statuses, record_refusals, store_key
from pathfinder.tests._support.provider_keys import sealed_provider_keys
from pathfinder.tests._support.provider_wire import (
    ProviderWire,
    allow_requests_to_the_wire,
)
from pathfinder.tests.integration.http.conftest import make_user

_KEY = "sk-proj-sentinel-0123456789WXYZ"


@dataclass
class _Chunks:
    """A chunk sink that keeps what a turn wrote."""

    conversation_id: UUID = field(default_factory=uuid4)
    turn_id: UUID = field(default_factory=uuid4)
    written: list[dict[str, Any]] = field(default_factory=list)

    async def write(self, chunk: dict[str, Any]) -> int:
        self.written.append(chunk)
        return len(self.written)

    def types(self) -> list[str]:
        return [str(chunk["type"]) for chunk in self.written]


@pytest.fixture
def _sealed(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with sealed_provider_keys(monkeypatch):
        yield


async def _keyed_user(
    session_maker: async_sessionmaker[AsyncSession], refused: bool
) -> UUID:
    async with session_maker() as session:
        user = await make_user(session)
        await store_key(session, user.id, "openai", SecretStr(_KEY))
        await session.commit()
    if refused:
        await record_refusals(user.id, {"openai": KeyRefusal.INVALID})
    return user.id


def _body() -> ChatRequestBody:
    return ChatRequestBody(conversation_id=uuid4())


@pytest.mark.usefixtures("_sealed", "patch_app_db_engine", "db_cleaner")
async def test_a_refused_key_closes_the_turn_before_it_runs(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _keyed_user(session_maker, refused=True)
    writer = _Chunks()
    ran = False

    with pytest.raises(ProviderKeyRefusedError):
        async with turn_keys(
            user_id=user_id, spec=build_pathfinder_spec(), body=_body(), writer=writer
        ):
            ran = True

    assert ran is False
    assert writer.types() == ["error", "data-turn-failed", "finish", "done"]


@pytest.mark.usefixtures("_sealed", "patch_app_db_engine", "db_cleaner")
async def test_a_key_refused_inside_the_turn_is_marked_after_it(
    session_maker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allow_requests_to_the_wire(monkeypatch)
    monkeypatch.setattr(get_settings(), "pathfinder_chat_provider", "default")
    user_id = await _keyed_user(session_maker, refused=False)
    wire = ProviderWire(refuse=True)

    async with turn_keys(
        user_id=user_id,
        spec=build_pathfinder_spec(),
        body=_body(),
        writer=_Chunks(),
        build=wire.build,
    ):
        assert turn_paid_by("openai:gpt-5.6-luna") is PaidBy.USER
        model = keyed_model("openai:gpt-5.6-luna")
        assert isinstance(model, Model)
        with pytest.raises(ProviderKeyRefusedError):
            await one_generation(model)

    async with session_maker() as session:
        assert await key_statuses(session, user_id) == KeyStatuses(
            refused={"openai": KeyRefusal.INVALID}
        )
    assert [h["authorization"] for h in wire.sent_headers()] == [f"Bearer {_KEY}"]


@pytest.mark.usefixtures("_sealed", "patch_app_db_engine", "db_cleaner")
async def test_the_turn_a_finished_task_opens_is_refused_on_a_refused_key(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    user_id = await _keyed_user(session_maker, refused=True)
    writer = _Chunks()
    result = DurableTaskResult(task_id=uuid4(), status="success")
    turn = CompletionTurn(
        spec=build_pathfinder_spec(),
        compiled_graph=cast("Any", None),
        memory_store=cast("Any", None),
        writer=writer,
        conversation_id=writer.conversation_id,
        user_id=user_id,
        phase_overrides=PhaseOverrides(),
        durable_result=result,
        durable_results=(result,),
    )

    with pytest.raises(ProviderKeyRefusedError):
        await open_completion_turn(turn)

    assert writer.types() == ["error", "data-turn-failed", "finish", "done"]
