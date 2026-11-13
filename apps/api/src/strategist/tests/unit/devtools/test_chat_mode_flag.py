from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from strategist.devtools import chat
from strategist.devtools.gates import BodyCtx, user_body


def _respond(tmp_path: Path, *extra: str) -> chat.RespondArgs:
    return chat.parse_respond_args(
        [
            "--site",
            "plasmodb",
            "--conversation-id",
            str(uuid4()),
            "--run-dir",
            str(tmp_path),
            *extra,
        ]
    )


def test_a_run_builds_unless_asked(tmp_path: Path) -> None:
    args = chat.parse_run_args(["hi", "--site", "plasmodb", "--run-dir", str(tmp_path)])

    body = user_body(chat._body_ctx(args), message_id=uuid4(), text="hi")

    assert body.mode == "build"


def test_a_run_sends_the_mode_it_names(tmp_path: Path) -> None:
    for mode in ("auto", "explore", "build"):
        args = chat.parse_run_args(
            ["hi", "--site", "plasmodb", "--run-dir", str(tmp_path), "--mode", mode]
        )

        body = user_body(chat._body_ctx(args), message_id=uuid4(), text="hi")

        assert body.mode == mode


def test_a_respond_builds_unless_asked(tmp_path: Path) -> None:
    assert chat._body_ctx(_respond(tmp_path)).mode == "build"


def test_a_respond_keeps_the_mode_it_names(tmp_path: Path) -> None:
    assert chat._body_ctx(_respond(tmp_path, "--mode", "explore")).mode == "explore"


def test_a_run_refuses_the_retired_strategy_mode(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        chat.parse_run_args(
            [
                "hi",
                "--site",
                "plasmodb",
                "--run-dir",
                str(tmp_path),
                "--mode",
                "strategy",
            ]
        )


def test_a_respond_refuses_the_retired_strategy_mode(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        _respond(tmp_path, "--mode", "strategy")


def test_a_body_context_builds_unless_told() -> None:
    assert BodyCtx(conversation_id=uuid4(), site_id="plasmodb").mode == "build"
