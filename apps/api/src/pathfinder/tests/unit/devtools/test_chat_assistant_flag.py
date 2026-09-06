"""``--assistant`` picks which assistant the debugger's turn runs under."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from pathfinder.devtools import chat
from pathfinder.platform.errors import AssistantMismatchError, AssistantNotFoundError

_RUN_ARGV = ["hi", "--site", "plasmodb", "--mock"]


def _install_existing(
    monkeypatch: pytest.MonkeyPatch,
    assistant_id: str | None,
) -> None:
    async def _read(_conversation_id: UUID) -> str | None:
        return assistant_id

    monkeypatch.setattr(
        "pathfinder.ai.conversation.assistant_routing.conversation_assistant_id",
        _read,
    )


def test_the_flag_is_absent_by_default() -> None:
    assert chat.parse_run_args(_RUN_ARGV).assistant is None


def test_the_flag_is_parsed_on_run_and_respond(tmp_path: Path) -> None:
    run = chat.parse_run_args([*_RUN_ARGV, "--assistant", "site_help"])
    respond = chat.parse_respond_args(
        [
            "--site",
            "plasmodb",
            "--conversation-id",
            str(uuid4()),
            "--run-dir",
            str(tmp_path),
            "--assistant",
            "site_help",
        ],
    )

    assert run.assistant == "site_help"
    assert respond.assistant == "site_help"


async def test_a_new_conversation_runs_under_the_named_assistant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_existing(monkeypatch, None)

    spec = await chat.resolve_run_assistant(uuid4(), "site_help")

    assert spec.assistant_id == "site_help"
    assert spec.identity_gate is None


async def test_no_flag_still_runs_under_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_existing(monkeypatch, None)

    spec = await chat.resolve_run_assistant(uuid4())

    assert spec.assistant_id == "pathfinder"


async def test_an_unknown_assistant_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_existing(monkeypatch, None)

    with pytest.raises(AssistantNotFoundError):
        await chat.resolve_run_assistant(uuid4(), "no_such_assistant")


async def test_naming_another_assistant_than_the_thread_s_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_existing(monkeypatch, "pathfinder")

    with pytest.raises(AssistantMismatchError):
        await chat.resolve_run_assistant(uuid4(), "site_help")
