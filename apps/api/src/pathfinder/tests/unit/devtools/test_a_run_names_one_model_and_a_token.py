"""A debugger or eval run pins one model for every role and reads its WDK token from a named variable."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic_ai.models import Model
from pydantic_ai.models.test import TestModel

from pathfinder.ai.agents import compactor
from pathfinder.ai.capabilities import security
from pathfinder.ai.capabilities.metering import SpendMeter
from pathfinder.ai.conversation import title_generator
from pathfinder.assistants.pathfinder_spec import build_pathfinder_spec
from pathfinder.assistants.registry import assistant_role_models
from pathfinder.devtools import chat, eval_runner, evals, run_models
from pathfinder.devtools.chat import EnvToken, RespondArgs, RunArgs
from pathfinder.devtools.gates import Gate
from pathfinder.evals.case import (
    CaseProvenance,
    EvalCase,
    ExpectedOutcome,
    GateEnd,
    GatePlan,
)
from pathfinder.evals.scoring import ObservedOutcome
from pathfinder.evals.summary import EvalRunSummary
from pathfinder.platform.config import get_settings
from pathfinder.platform.model_catalog import get_smallest_model
from pathfinder.platform.pinned_model import pinned_model
from pathfinder.platform.stage_sites import qa_sites_file
from pathfinder.tests._support.models import OPENAI_FLAGSHIP

LUNA = "openai:gpt-5.6-luna"
_TOKEN = "qa-token-sentinel-0123"
_QA = str(qa_sites_file())
_EVERY_ROLE = {
    "lead",
    "frame",
    "execution",
    "verification",
    "title_generator",
    "note_compactor",
    "injection_judge",
}


@pytest.fixture(autouse=True)
def _quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PF_QA_TOKEN", raising=False)
    monkeypatch.setattr(chat, "route_framework_logs_to_stderr", lambda: None)


@pytest.fixture
def no_sign_in(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    attempts: list[str] = []

    async def _refused(site: str, email: str, password: str) -> str | None:
        del email, password
        attempts.append(site)
        msg = "a token run signs in with no password"
        raise AssertionError(msg)

    async def _registered() -> None:
        return None

    monkeypatch.setattr(chat, "password_login", _refused)
    monkeypatch.setattr(chat, "require_registered_wdk_login", _registered)
    return attempts


def test_every_role_resolves_to_the_pinned_model() -> None:
    with run_models.pin_every_role(LUNA):
        assert run_models.resolved_roles() == dict.fromkeys(_EVERY_ROLE, LUNA)


def test_the_pin_moves_every_role_off_its_own_model() -> None:
    before = run_models.resolved_roles()

    with run_models.pin_every_role(OPENAI_FLAGSHIP):
        pinned = run_models.resolved_roles()

    assert set(before.values()) != {OPENAI_FLAGSHIP}
    assert pinned == dict.fromkeys(_EVERY_ROLE, OPENAI_FLAGSHIP)


def test_outside_a_pinned_run_every_role_resolves_as_before() -> None:
    settings = get_settings()
    smallest = get_smallest_model(settings.default_provider).id
    unpinned = {
        **assistant_role_models("pathfinder", {}),
        "title_generator": smallest,
        "note_compactor": smallest,
        "injection_judge": settings.input_screening_model,
    }
    assert run_models.resolved_roles() == unpinned

    with run_models.pin_every_role(OPENAI_FLAGSHIP):
        pass

    assert pinned_model() is None
    assert run_models.resolved_roles() == unpinned
    assert run_models.pinned_phase_models() == {}


async def test_the_title_generator_builds_on_the_pinned_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "pathfinder_chat_provider", "default")
    built: list[str] = []

    def _keyed(model_id: str) -> Model:
        built.append(model_id)
        return TestModel(custom_output_text="Kinase Survey")

    monkeypatch.setattr(title_generator, "keyed_model", _keyed)

    with run_models.pin_every_role(LUNA):
        title = await title_generator.generate_conversation_title(
            "list the kinases", build_pathfinder_spec().build_mock_model, SpendMeter()
        )

    assert built == [LUNA]
    assert title == "Kinase Survey"


def test_the_note_compactor_builds_on_the_pinned_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    built: list[str] = []

    def _keyed(model_id: str) -> Model:
        built.append(model_id)
        return TestModel()

    monkeypatch.setattr(compactor, "keyed_model", _keyed)

    with run_models.pin_every_role(LUNA):
        compactor.build_compactor_agent(meter=SpendMeter())
    compactor.build_compactor_agent(meter=SpendMeter())

    assert built == [LUNA, get_smallest_model(get_settings().default_provider).id]


def test_the_injection_judge_is_built_on_the_model_in_force(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "pathfinder_chat_provider", "default")
    built: list[str] = []

    def _deployment(model_id: str) -> Model:
        built.append(model_id)
        return TestModel()

    monkeypatch.setattr(security, "deployment_model", _deployment)
    security._judge_on.cache_clear()
    try:
        before = security._judge()
        with run_models.pin_every_role(OPENAI_FLAGSHIP):
            pinned = security._judge()
        after = security._judge()
    finally:
        security._judge_on.cache_clear()

    assert built == [get_settings().input_screening_model, OPENAI_FLAGSHIP]
    assert after is before
    assert pinned is not before


def test_the_requests_a_pinned_run_sends_pin_every_role(tmp_path: Path) -> None:
    args = chat.parse_run_args(["hi", "--site", "orthomcl", "--run-dir", str(tmp_path)])

    with run_models.pin_every_role(LUNA):
        chat.write_turn_settings(args, assistant_id="pathfinder")

    sent = json.loads((tmp_path / chat.TURN_SETTINGS_FILE).read_text())
    assert sent["phaseModels"] == {
        "lead": LUNA,
        "frame": LUNA,
        "execution": LUNA,
        "verification": LUNA,
    }


def test_an_unknown_model_is_refused_by_name() -> None:
    with (
        pytest.raises(run_models.RunModelError, match="openai:no-such-model"),
        run_models.pin_every_role("openai:no-such-model"),
    ):
        pass

    assert pinned_model() is None


def _chat(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr("sys.argv", ["chat", *argv])
    with pytest.raises(SystemExit) as exited:
        chat.main()
    code = exited.value.code
    assert isinstance(code, int)
    return code


def test_roles_exits_zero_when_every_role_is_on_the_model(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PF_QA_TOKEN", _TOKEN)

    code = _chat(
        monkeypatch, ["roles", "--model-all", LUNA, "--wdk-token-env", "PF_QA_TOKEN"]
    )

    printed = capsys.readouterr().out.splitlines()
    assert code == 0
    assert printed == [
        f"execution: {LUNA}",
        f"frame: {LUNA}",
        f"injection_judge: {LUNA}",
        f"lead: {LUNA}",
        f"note_compactor: {LUNA}",
        f"title_generator: {LUNA}",
        f"verification: {LUNA}",
        "identity: WDK token from $PF_QA_TOKEN",
    ]


def test_roles_names_a_role_on_another_model_and_exits_non_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(security, "judge_model_id", lambda: OPENAI_FLAGSHIP)

    code = _chat(monkeypatch, ["roles", "--model-all", LUNA])

    captured = capsys.readouterr()
    assert code == 1
    assert f"injection_judge: {OPENAI_FLAGSHIP}" in captured.out.splitlines()
    assert "identity: password sign-in" in captured.out
    assert captured.err.strip().endswith(
        f"not on {LUNA}: injection_judge ({OPENAI_FLAGSHIP})"
    )


def test_roles_refuses_an_unknown_model_by_name(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _chat(monkeypatch, ["roles", "--model-all", "openai:no-such-model"])

    assert code == 2
    assert "openai:no-such-model" in capsys.readouterr().err


async def test_the_chat_driver_attaches_the_named_token_without_a_sign_in(
    monkeypatch: pytest.MonkeyPatch, no_sign_in: list[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("PF_QA_TOKEN", _TOKEN)
    common = ["--site", "orthomcl", "--wdk-token-env", "PF_QA_TOKEN"]
    run = chat.parse_run_args(["hi", *common, "--run-dir", str(tmp_path)])
    respond = chat.parse_respond_args(
        [
            *common,
            "--run-dir",
            str(tmp_path),
            "--conversation-id",
            "00000000-0000-0000-0000-000000000001",
        ]
    )

    assert await chat._optional_wdk_token(run) == _TOKEN
    assert await chat._optional_wdk_token(respond) == _TOKEN
    assert no_sign_in == []
    assert _TOKEN not in repr(run)
    assert _TOKEN not in run.model_dump_json()


@pytest.mark.parametrize("value", ["", "   "])
def test_an_empty_variable_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("PF_QA_TOKEN", value)

    with pytest.raises(chat.MissingCredentialsError, match=r"\$PF_QA_TOKEN"):
        chat.parse_run_args(
            ["hi", "--site", "orthomcl", "--wdk-token-env", "PF_QA_TOKEN"]
        )


def test_an_unset_variable_is_refused_by_name() -> None:
    with pytest.raises(chat.MissingCredentialsError, match=r"\$PF_QA_TOKEN"):
        EnvToken.read("PF_QA_TOKEN")


@pytest.mark.usefixtures("restored_sites_file")
def test_a_chat_run_refuses_an_empty_variable_before_the_turn(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    code = _chat(
        monkeypatch,
        [
            "run",
            "hi",
            "--site",
            "orthomcl",
            "--run-dir",
            str(tmp_path / "turn"),
            "--wdk-token-env",
            "PF_QA_TOKEN",
        ],
    )

    assert code == 2
    assert "$PF_QA_TOKEN" in capsys.readouterr().err
    assert not (tmp_path / "turn").exists()


@pytest.mark.usefixtures("restored_sites_file")
def test_a_chat_run_refuses_a_pin_the_worker_would_not_read(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VEUPATHDB_SITES_CONFIG", _QA)
    code = _chat(
        monkeypatch,
        [
            "run",
            "hi",
            "--site",
            "orthomcl",
            "--sites",
            _QA,
            "--run-dir",
            str(tmp_path / "turn"),
            "--model-all",
            LUNA,
            "--via-worker",
        ],
    )

    assert code == 2
    assert "--via-worker" in capsys.readouterr().err


def test_a_pin_and_a_per_role_model_do_not_combine() -> None:
    with pytest.raises(SystemExit):
        chat.parse_run_args(
            ["hi", "--site", "orthomcl", "--model-all", LUNA, "--model", f"lead={LUNA}"]
        )


def _summary() -> EvalRunSummary:
    return EvalRunSummary(
        harness="pydantic-evals",
        provider="default",
        assistant_id="pathfinder",
        ran_at="2026-10-22T00:00:00+00:00",
        cases=[],
    )


@pytest.mark.usefixtures("restored_sites_file")
def test_an_eval_run_pins_the_model_reads_the_token_and_prints_the_roles(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PF_QA_TOKEN", _TOKEN)
    received: dict[str, object] = {}

    async def _run_corpus(**options: object) -> EvalRunSummary:
        received.update(options)
        received["roles"] = run_models.resolved_roles()
        return _summary()

    monkeypatch.setattr(evals, "run_corpus", _run_corpus)

    code = evals.main(
        ["run", "--sites", _QA, "--model", LUNA, "--wdk-token-env", "PF_QA_TOKEN"]
    )

    printed = capsys.readouterr().out.splitlines()
    token = received["wdk_token"]
    assert code == 0
    assert isinstance(token, EnvToken)
    assert token.token.get_secret_value() == _TOKEN
    assert received["roles"] == dict.fromkeys(_EVERY_ROLE, LUNA)
    assert printed[:8] == printed[-9:-1]
    assert f"lead: {LUNA}" in printed[:8]
    assert printed[7] == "identity: WDK token from $PF_QA_TOKEN"


@pytest.mark.usefixtures("restored_sites_file")
@pytest.mark.parametrize(
    ("argv", "named"),
    [
        (["--model", "openai:no-such-model"], "openai:no-such-model"),
        (["--wdk-token-env", "PF_QA_TOKEN"], "$PF_QA_TOKEN"),
        (["--model", LUNA, "--via-worker"], "--via-worker"),
    ],
)
def test_an_eval_run_refuses_before_the_first_case(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    argv: list[str],
    named: str,
) -> None:
    ran: list[object] = []

    async def _run_corpus(**options: object) -> EvalRunSummary:
        ran.append(options)
        return _summary()

    monkeypatch.setattr(evals, "run_corpus", _run_corpus)
    monkeypatch.setenv("VEUPATHDB_SITES_CONFIG", _QA)

    code = evals.main(["run", "--sites", _QA, *argv])

    assert code == 2
    assert ran == []
    assert named in capsys.readouterr().err


class _Capture:
    def assistant_text(self) -> str:
        return "a reply"

    def turn_facts(self) -> None:
        return None

    def refused_tools(self) -> list[str]:
        return []


def _case() -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=["build it"],
        site_id="orthomcl",
        assistant_id="pathfinder",
        rationale="pins a thing",
        expected=ExpectedOutcome(builds_strategy=True),
        gates=GatePlan(policy="auto"),
        provenance=CaseProvenance(
            site="orthomcl",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-10-22",
        ),
    )


async def test_the_eval_driver_attaches_the_named_token_on_every_turn_and_answer(
    monkeypatch: pytest.MonkeyPatch, no_sign_in: list[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("PF_QA_TOKEN", _TOKEN)
    driven: list[RunArgs] = []
    answered: list[RespondArgs] = []

    async def _drive(args: RunArgs) -> tuple[_Capture, Gate]:
        driven.append(args)
        return _Capture(), Gate(kind="approval", tool="delete_step", tool_call_id="c1")

    async def _respond(args: RespondArgs) -> tuple[_Capture, Gate]:
        answered.append(args)
        return _Capture(), Gate(kind="none")

    async def _nothing(conversation_id: UUID) -> None:
        del conversation_id

    async def _no_steps(conversation_id: UUID) -> set[int]:
        del conversation_id
        return set()

    async def _observe(
        conversation_id: UUID,
        turns: eval_runner.TurnsShown,
        *,
        step_ids_unchanged: bool | None,
        ends_on: GateEnd | None,
        refused_tools: list[str],
    ) -> ObservedOutcome:
        del conversation_id, turns, step_ids_unchanged, ends_on
        return ObservedOutcome(built_strategy=True, refused_tools=refused_tools)

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    monkeypatch.setattr(eval_runner, "drive_respond", _respond)
    monkeypatch.setattr(eval_runner, "persisted_wdk_step_ids", _no_steps)
    monkeypatch.setattr(eval_runner, "reviewed_checks", _nothing)
    monkeypatch.setattr(eval_runner, "observe", _observe)
    monkeypatch.setattr(eval_runner, "forget_user", _nothing)

    await eval_runner.run_one_case(
        _case(), run_root=tmp_path, wdk_token=EnvToken.read("PF_QA_TOKEN")
    )

    assert [await chat._optional_wdk_token(a) for a in [*driven, *answered]] == [
        _TOKEN,
        _TOKEN,
    ]
    assert no_sign_in == []
