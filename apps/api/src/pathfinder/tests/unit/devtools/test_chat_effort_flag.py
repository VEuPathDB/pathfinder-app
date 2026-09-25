"""The debugger's ``--effort`` flag sets every role's reasoning effort on the
turn's request body, and the run directory records it."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from pathfinder.devtools import chat
from pathfinder.devtools.gates import user_body
from pathfinder.platform.tiers import KNOWN_ROLES


def test_the_flag_sets_every_roles_reasoning_on_the_turn(tmp_path: Path) -> None:
    args = chat.parse_run_args(
        ["hi", "--site", "plasmodb", "--run-dir", str(tmp_path), "--effort", "high"]
    )

    body = user_body(chat._body_ctx(args), message_id=uuid4(), text="hi")

    assert body.runtime_phase_reasoning == dict.fromkeys(KNOWN_ROLES, "high")
    assert body.runtime_phase_reasoning["lead"] == "high"


def test_without_the_flag_each_role_keeps_its_tier_effort(tmp_path: Path) -> None:
    args = chat.parse_run_args(["hi", "--site", "plasmodb", "--run-dir", str(tmp_path)])

    body = user_body(chat._body_ctx(args), message_id=uuid4(), text="hi")

    assert body.runtime_phase_reasoning == {}


def test_a_resumed_gate_keeps_the_effort(tmp_path: Path) -> None:
    args = chat.parse_respond_args(
        [
            "--site",
            "plasmodb",
            "--conversation-id",
            str(uuid4()),
            "--run-dir",
            str(tmp_path),
            "--effort",
            "low",
        ]
    )

    assert chat._body_ctx(args).phase_reasoning == dict.fromkeys(KNOWN_ROLES, "low")


def test_an_effort_the_request_body_does_not_take_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        chat.parse_run_args(
            ["hi", "--site", "plasmodb", "--run-dir", str(tmp_path), "--effort", "max"]
        )


def test_the_run_directory_records_the_effort(tmp_path: Path) -> None:
    args = chat.parse_run_args(
        ["hi", "--site", "plasmodb", "--run-dir", str(tmp_path), "--effort", "high"]
    )

    chat.write_turn_settings(args, assistant_id="pathfinder")

    recorded = json.loads((tmp_path / "turn_settings.json").read_text())
    assert recorded == {
        "assistantId": "pathfinder",
        "phaseModels": {},
        "phaseReasoning": dict.fromkeys(KNOWN_ROLES, "high"),
    }


def test_a_run_directory_that_does_not_exist_yet_is_created(tmp_path: Path) -> None:
    run_dir = tmp_path / "sweep" / "turn-2"
    args = chat.parse_run_args(["hi", "--site", "plasmodb", "--run-dir", str(run_dir)])

    chat.write_turn_settings(args, assistant_id="pathfinder")

    assert json.loads((run_dir / "turn_settings.json").read_text())["assistantId"] == (
        "pathfinder"
    )
