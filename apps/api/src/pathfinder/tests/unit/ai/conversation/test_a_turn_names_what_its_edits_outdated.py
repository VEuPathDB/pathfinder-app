"""The turn's end writes the first title, or a generated name its edits outdated."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from veupathdb.domain.strategy import StrategyAst

from pathfinder.ai.conversation import turn_title

_TITLE = "Naegleria fowleri Peptidase Genes With Signal Peptides"
_RENAMED = "Naegleria fowleri Genes With Signal Peptides"


@dataclass
class _Writer:
    conversation_id: UUID = field(default_factory=uuid4)
    turn_id: UUID = field(default_factory=uuid4)
    chunks: list[dict[str, Any]] = field(default_factory=list)

    async def write(self, chunk: dict[str, Any]) -> int:
        self.chunks.append(chunk)
        return len(self.chunks)


@dataclass
class _Renames:
    """The service that renames after edits, answering one name."""

    answer: str | None = _RENAMED
    failure: Exception | None = None
    calls: list[UUID] = field(default_factory=list)

    async def __call__(
        self, conversation_id: UUID, *, start: StrategyAst | None, title_for: object
    ) -> str | None:
        del start, title_for
        self.calls.append(conversation_id)
        if self.failure is not None:
            raise self.failure
        return self.answer


async def _no_title(seed: str) -> str:
    del seed
    return ""


def _install(
    monkeypatch: pytest.MonkeyPatch,
    renames: _Renames,
    *,
    titled: bool,
    offered: list[str | None] | None = None,
) -> None:
    async def _named(conversation_id: UUID, *, title: str | None) -> bool:
        del conversation_id
        if offered is not None:
            offered.append(title)
        return titled

    monkeypatch.setattr(turn_title, "name_conversation_if_unnamed", _named)
    monkeypatch.setattr(turn_title, "rename_if_edits_outdated_it", renames)


async def _title() -> str:
    return _TITLE


async def _name(writer: _Writer, *, with_title: bool = True) -> None:
    await turn_title.write_turn_name(
        asyncio.create_task(_title()) if with_title else None,
        writer.conversation_id,
        writer,
        start=None,
        title_for=_no_title,
    )


def _titles(writer: _Writer) -> list[str]:
    return [
        chunk["data"]["title"]
        for chunk in writer.chunks
        if chunk["type"] == "data-conversation-title"
    ]


async def test_a_turn_that_wrote_the_first_title_checks_no_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renames = _Renames()
    _install(monkeypatch, renames, titled=True)
    writer = _Writer()

    await _name(writer)

    assert (_titles(writer), renames.calls) == ([_TITLE], [])


async def test_a_name_an_edit_outdated_is_written_as_the_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renames = _Renames()
    _install(monkeypatch, renames, titled=False)
    writer = _Writer()

    await _name(writer)

    assert (_titles(writer), renames.calls) == ([_RENAMED], [writer.conversation_id])


async def test_a_turn_with_no_message_still_checks_its_edits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renames = _Renames()
    _install(monkeypatch, renames, titled=False)
    writer = _Writer()

    await _name(writer, with_title=False)

    assert _titles(writer) == [_RENAMED]


async def test_a_turn_with_no_title_still_puts_the_thread_name_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    offered: list[str | None] = []
    _install(monkeypatch, _Renames(answer=None), titled=False, offered=offered)

    await _name(_Writer(), with_title=False)

    assert offered == [None]


async def test_a_name_that_stands_writes_no_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, _Renames(answer=None), titled=False)
    writer = _Writer()

    await _name(writer)

    assert writer.chunks == []


@pytest.mark.parametrize("failure", [RuntimeError("store closed"), TimeoutError()])
async def test_a_rename_that_fails_leaves_the_turn_to_finish(
    monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    _install(monkeypatch, _Renames(failure=failure), titled=False)
    writer = _Writer()

    await _name(writer)

    assert writer.chunks == []
