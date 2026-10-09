from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from veupathdb.wdk import SearchRequest
from veupathdb_mcp.search_line import search_line_gate

from pathfinder.ai.conversation import turn_runner
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.tests._support.search_load import TEXT_REPORT, a_counted_site


class _TurnEndedError(RuntimeError):
    pass


@dataclass
class _Writer:
    conversation_id: UUID = field(default_factory=uuid4)
    turn_id: UUID = field(default_factory=uuid4)
    chunks: list[dict[str, Any]] = field(default_factory=list)
    status_seen: asyncio.Event = field(default_factory=asyncio.Event)

    async def write(self, chunk: dict[str, Any]) -> int:
        self.chunks.append(chunk)
        if chunk["type"] == "data-turn-status":
            self.status_seen.set()
        return len(self.chunks)

    def labels(self) -> list[str]:
        return [
            c["data"]["label"] for c in self.chunks if c["type"] == "data-turn-status"
        ]


def _body(writer: _Writer) -> ChatRequestBody:
    return ChatRequestBody.model_validate(
        {
            "conversationId": str(writer.conversation_id),
            "messages": [
                {
                    "id": str(uuid4()),
                    "role": "user",
                    "parts": [{"type": "text", "text": "hi"}],
                },
            ],
            "siteId": "plasmodb",
        },
    )


def _spec() -> Any:
    class _Spec:
        tool_sources: tuple[Any, ...] = ()

    return _Spec()


async def _run(writer: _Writer) -> None:
    with pytest.raises(_TurnEndedError):
        await turn_runner.run_turn(
            request=turn_runner.TurnRequest(body=_body(writer), user_id=uuid4()),
            spec=_spec(),
            compiled_graph=None,
            memory_store=None,
            writer=writer,
        )


async def test_two_searches_of_one_turn_reach_the_site_one_at_a_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with a_counted_site() as (client, load):

        async def two_searches(conversation_id: UUID) -> None:
            del conversation_id
            await asyncio.gather(
                client.post(TEXT_REPORT, json={}), client.post(TEXT_REPORT, json={})
            )
            raise _TurnEndedError

        monkeypatch.setattr(turn_runner, "load_conversation", two_searches)
        await _run(_Writer())

    assert (load.answered, load.most_in_flight) == (2, 1)


async def test_a_turn_waiting_for_the_expensive_line_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = _Writer()

    class _Line:
        @asynccontextmanager
        async def hold(self, site_id: str) -> AsyncIterator[None]:
            del site_id
            async with asyncio.timeout(5):
                await writer.status_seen.wait()
            yield

    async def an_expensive_search(conversation_id: UUID) -> None:
        del conversation_id
        request = SearchRequest(
            site_id="plasmodb",
            kind="report",
            search_names=frozenset({"GenesByNgsSnps"}),
        )
        async with search_line_gate(_Line(), notice_seconds=0.0)(request):
            raise _TurnEndedError

    monkeypatch.setattr(turn_runner, "load_conversation", an_expensive_search)
    await _run(writer)

    assert writer.labels() == ["Waiting for PlasmoDB", ""]
