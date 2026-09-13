from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import structlog
from assistant_core.persistence.models import Conversation
from assistant_core.platform.context import (
    DEFAULT_APPLICATION_ID,
    application_id_ctx,
)
from assistant_core.platform.db import async_session_factory
from pydantic import BaseModel, ConfigDict, Field

from pathfinder.assistants.site_help.mock import SITES_REPLY
from pathfinder.devtools import chat
from pathfinder.devtools.capture import RunCapture
from pathfinder.devtools.chat import (
    DEV_USER_ID,
    MissingCredentialsError,
    RunArgs,
    _body_ctx,
    _gate_from_checkpoint,
    _optional_wdk_token,
    _wdk_token,
    _worker_payload,
    parse_respond_args,
    parse_run_args,
    route_framework_logs_to_stderr,
    run_once,
    run_respond,
)
from pathfinder.devtools.gates import user_body
from pathfinder.persistence.repositories.user import UserRepository
from pathfinder.platform.config import get_settings
from pathfinder.platform.durable_worker import durable_call_refusal
from pathfinder.platform.identity import PATHFINDER_APPLICATION_ID
from pathfinder.services.conversations.begin import begin_conversation

# The durable tool the Lead calls on a saved set, under the name the model uses.
ENRICHMENT_TOOL = "run_gene_set_enrichment"


def test_parse_run_args_maps_phase_models_and_run_dir(tmp_path: Path) -> None:
    args = parse_run_args(
        [
            "hello",
            "--site",
            "plasmodb",
            "--model",
            "frame=openai:gpt-5.6-luna",
            "--run-dir",
            str(tmp_path / "r"),
        ]
    )
    assert args.prompt == "hello"
    assert args.site == "plasmodb"
    assert args.phase_models == {"frame": "openai:gpt-5.6-luna"}
    assert args.approve == "prompt"
    assert args.run_dir == tmp_path / "r"


def test_parse_run_args_mints_distinct_conversation_ids() -> None:
    a = parse_run_args(["hi", "--site", "plasmodb"])
    b = parse_run_args(["hi", "--site", "plasmodb"])
    assert a.conversation_id != b.conversation_id


async def test_wdk_token_missing_creds_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("WDK_DEV_EMAIL", raising=False)
    monkeypatch.delenv("WDK_DEV_PASSWORD", raising=False)
    args = parse_run_args(
        ["hi", "--site", "plasmodb", "--run-dir", str(tmp_path / "r")]
    )
    with pytest.raises(MissingCredentialsError, match="WDK_DEV_EMAIL"):
        await _wdk_token(args)


async def test_a_mocked_run_without_credentials_does_not_log_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the LLM is mocked, so the login is skipped only when it cannot run."""
    monkeypatch.delenv("WDK_DEV_EMAIL", raising=False)
    monkeypatch.delenv("WDK_DEV_PASSWORD", raising=False)
    args = parse_run_args(
        ["hi", "--site", "plasmodb", "--mock", "--run-dir", str(tmp_path / "r")]
    )

    assert await _optional_wdk_token(args) is None


async def test_a_mocked_run_with_credentials_logs_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WDK is real in a mocked run, so a strategy it builds reaches the site."""
    monkeypatch.setenv("WDK_DEV_EMAIL", "someone@example.org")
    monkeypatch.setenv("WDK_DEV_PASSWORD", "not-a-real-password")

    async def _login(site: str, email: str, password: str) -> str:
        del site, email, password
        return "token-from-login"

    monkeypatch.setattr(chat, "password_login", _login)
    args = parse_run_args(
        ["hi", "--site", "plasmodb", "--mock", "--run-dir", str(tmp_path / "r")]
    )

    assert await _optional_wdk_token(args) == "token-from-login"


def test_route_framework_logs_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    structlog.reset_defaults()
    try:
        route_framework_logs_to_stderr()
        structlog.get_logger("pathfinder.devtools.test").info("framework chatter X")
        out = capsys.readouterr()
        assert "framework chatter X" in out.err
        assert "framework chatter X" not in out.out
    finally:
        structlog.reset_defaults()


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_run_once_resets_stale_run_dir(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "tools").mkdir(parents=True)
    stale = run_dir / "tools" / "99-stale_tool.json"
    stale.write_text('{"seq": 99, "tool": "stale_tool", "status": "failed"}')
    args = parse_run_args(
        [
            "delegation",
            "--site",
            "plasmodb",
            "--mock",
            "--approve",
            "auto",
            "--quiet",
            "--run-dir",
            str(run_dir),
        ]
    )
    code = await run_once(args)
    assert code == 0
    assert not stale.exists()


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_a_debugger_run_stamps_this_application(tmp_path: Path) -> None:
    """The debugger serves no request, so it names the application itself."""
    conv = uuid4()
    args = parse_run_args(
        [
            "delegation",
            "--site",
            "plasmodb",
            "--mock",
            "--approve",
            "auto",
            "--quiet",
            "--conversation-id",
            str(conv),
            "--run-dir",
            str(tmp_path / "run"),
        ]
    )
    reset = application_id_ctx.set(DEFAULT_APPLICATION_ID)
    try:
        await run_once(args)
    finally:
        application_id_ctx.reset(reset)

    async with async_session_factory() as session:
        row = await session.get(Conversation, conv)
    assert row is not None
    assert row.application_id == PATHFINDER_APPLICATION_ID


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_capture_wdk_records_into_the_run_dir(tmp_path: Path) -> None:
    """The flag enters the client's capture, which owns the ``wdk/`` directory."""
    plain, captured = tmp_path / "plain", tmp_path / "captured"

    def _args(run_dir: Path, *extra: str) -> list[str]:
        return [
            "delegation",
            "--site",
            "plasmodb",
            "--mock",
            "--approve",
            "auto",
            "--quiet",
            "--run-dir",
            str(run_dir),
            *extra,
        ]

    await run_once(parse_run_args(_args(plain)))
    await run_once(parse_run_args(_args(captured, "--capture-wdk")))

    assert not (plain / "wdk").exists()
    assert (captured / "wdk").is_dir()


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_run_prompt_stops_at_gate_then_respond_advances(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    conv = uuid4()
    run_args = parse_run_args(
        [
            "delegation",
            "--site",
            "plasmodb",
            "--mock",
            "--approve",
            "prompt",
            "--quiet",
            "--conversation-id",
            str(conv),
            "--run-dir",
            str(run_dir),
        ]
    )
    await run_once(run_args)
    gate = json.loads((run_dir / "gate.json").read_text())
    assert gate["kind"] in {"none", "approval", "consult"}

    if gate["kind"] in {"approval", "consult"}:
        flag = "--accept" if gate["kind"] == "approval" else "--answer"
        extra = [] if gate["kind"] == "approval" else ["q=x"]
        resp_args = parse_respond_args(
            [
                "--site",
                "plasmodb",
                "--mock",
                "--approve",
                "auto",
                "--quiet",
                "--conversation-id",
                str(conv),
                "--run-dir",
                str(run_dir),
                flag,
                *extra,
            ]
        )
        code = await run_respond(resp_args)
        assert code == 0
        # respond advanced the turn (events grew, gate re-derived)
        assert (run_dir / "gate.json").exists()


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_respond_finds_gate_from_checkpoint_not_run_dir(tmp_path: Path) -> None:
    """The pending gate is derived from the conversation checkpoint (SSOT), so
    ``respond`` finds it without --run-dir pointing at the gate's turn."""
    run_dir = tmp_path / "run"
    conv = uuid4()
    run_args = parse_run_args(
        [
            "consult me before planning: find female-enriched genes",
            "--site",
            "plasmodb",
            "--mock",
            "--approve",
            "prompt",
            "--quiet",
            "--conversation-id",
            str(conv),
            "--run-dir",
            str(run_dir),
        ]
    )
    await run_once(run_args)
    gate = json.loads((run_dir / "gate.json").read_text())
    assert gate["kind"] == "consult", gate

    # An operator running ``respond`` from a fresh run-dir knows nothing about
    # the turn that produced the gate — the checkpoint must surface it.
    settings = get_settings()
    derived = await _gate_from_checkpoint(conv, settings.database_url)
    assert derived.kind == "consult"
    assert derived.tool == "consult_user"
    assert derived.tool_call_id == gate["toolCallId"]
    assert {q.id for q in derived.consult_questions} == {"q1", "q2"}


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_a_site_help_run_answers_in_process_with_no_wdk_login(
    tmp_path: Path,
) -> None:
    """The second assistant runs through the same debugger, and needs no login."""
    run_dir = tmp_path / "run"
    args = parse_run_args(
        [
            "which sites can I search",
            "--site",
            "plasmodb",
            "--mock",
            "--assistant",
            "site_help",
            "--quiet",
            "--run-dir",
            str(run_dir),
        ]
    )

    code = await run_once(args)

    assert code == 0
    events = [
        json.loads(line)
        for line in (run_dir / "events.jsonl").read_text().splitlines()
        if line.strip()
    ]
    called = [e["toolName"] for e in events if e["type"] == "tool-input-available"]
    assert called == ["list_veupathdb_sites"]
    text = "".join(e["delta"] for e in events if e["type"] == "text-delta")
    assert text == SITES_REPLY
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["status"] == "ok"


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_run_once_mock_writes_artifacts_and_exits_clean(tmp_path: Path) -> None:
    args = parse_run_args(
        [
            "delegation",
            "--site",
            "plasmodb",
            "--mock",
            "--approve",
            "auto",
            "--quiet",
            "--run-dir",
            str(tmp_path / "run"),
        ]
    )
    code = await run_once(args)
    assert code == 0
    assert isinstance(args, RunArgs)
    run_dir = tmp_path / "run"
    assert (run_dir / "events.jsonl").exists()
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["status"] == "ok"
    assert (run_dir / "diagnosis.json").exists()


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_run_once_leaves_the_global_logger_config_alone(tmp_path: Path) -> None:
    """Only the command line routes framework logs; a driven run does not."""
    before = structlog.get_config()
    args = parse_run_args(
        [
            "delegation",
            "--site",
            "plasmodb",
            "--mock",
            "--approve",
            "auto",
            "--quiet",
            "--run-dir",
            str(tmp_path / "run"),
        ]
    )

    await run_once(args)

    assert structlog.get_config() == before


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_the_worker_payload_names_the_thread_s_assistant(tmp_path: Path) -> None:
    """A worker run of the second assistant must not defer PathFinder's turn."""
    conversation_id = uuid4()
    args = parse_run_args(
        [
            "which sites can I search",
            "--site",
            "plasmodb",
            "--mock",
            "--assistant",
            "site_help",
            "--quiet",
            "--conversation-id",
            str(conversation_id),
            "--run-dir",
            str(tmp_path / "run"),
        ]
    )
    async with async_session_factory() as session:
        await UserRepository(session).get_or_create(DEV_USER_ID)
        await begin_conversation(
            session=session,
            conversation_id=conversation_id,
            user_id=DEV_USER_ID,
            site_id="plasmodb",
            assistant_id="site_help",
        )
        await session.commit()
    capture = RunCapture(
        conversation_id=conversation_id,
        turn_id=uuid4(),
        run_dir=args.run_dir,
        quiet=True,
    )

    body = user_body(_body_ctx(args), message_id=capture.turn_id, text=args.prompt)

    payload = await _worker_payload(args, capture, body, wdk_token=None)

    assert payload.assistant_id == "site_help"


class _ToolChunk(BaseModel):
    """The two chunks that name a tool call and carry what answered it."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    type: str = ""
    tool_call_id: str = Field(default="", alias="toolCallId")
    tool_name: str = Field(default="", alias="toolName")
    output: Any = None


def _tool_chunks(run_dir: Path) -> list[_ToolChunk]:
    lines = (run_dir / "events.jsonl").read_text().splitlines()
    return [
        _ToolChunk.model_validate(json.loads(line)) for line in lines if line.strip()
    ]


def _answers_to(run_dir: Path, tool_name: str) -> list[Any]:
    """What each call of this tool was answered with, in order."""
    chunks = _tool_chunks(run_dir)
    called = {
        chunk.tool_call_id
        for chunk in chunks
        if chunk.type == "tool-input-available" and chunk.tool_name == tool_name
    }
    return [
        chunk.output
        for chunk in chunks
        if chunk.type == "tool-output-available" and chunk.tool_call_id in called
    ]


@pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")
async def test_a_durable_call_is_declined_and_the_run_writes_its_artifacts(
    tmp_path: Path,
) -> None:
    """The debugger runs no worker, so the turn ends with the refusal on record."""
    args = parse_run_args(
        [
            "Run a GO enrichment on the gene set I saved",
            "--site",
            "plasmodb",
            "--mock",
            "--approve",
            "auto",
            "--quiet",
            "--run-dir",
            str(tmp_path / "run"),
        ]
    )

    code = await run_once(args)

    assert code == 0
    run_dir = tmp_path / "run"
    summary = json.loads((run_dir / "summary.json").read_text())
    assert summary["status"] == "ok"
    transcript = (run_dir / "transcript.md").read_text()
    assert f"[lead] {ENRICHMENT_TOOL}" in transcript
    assert durable_call_refusal(ENRICHMENT_TOOL) in transcript
    assert _answers_to(run_dir, ENRICHMENT_TOOL) == [
        durable_call_refusal(ENRICHMENT_TOOL)
    ]
