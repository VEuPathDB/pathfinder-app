"""A debugger or eval run refuses a role off its model and a token that names no login before any turn or case."""

from __future__ import annotations

import ast
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from pydantic_ai.ui.vercel_ai.request_types import TextUIPart, UIMessage
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import WDKLoginRequiredError

import pathfinder
from pathfinder.ai.capabilities import security
from pathfinder.ai.conversation.request_body import ChatRequestBody
from pathfinder.devtools import chat, eval_runner, evals, run_models
from pathfinder.devtools.capture import RunCapture
from pathfinder.devtools.chat import EnvToken
from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome, GatePlan
from pathfinder.evals.scoring import ObservedOutcome
from pathfinder.evals.summary import EvalRunSummary
from pathfinder.platform.model_catalog import get_model_catalog
from pathfinder.platform.stage_sites import qa_sites_file
from pathfinder.tests._support.models import OPENAI_FLAGSHIP

LUNA = "openai:gpt-5.6-luna"
_TOKEN = "qa-token-sentinel-4567"
_QA = str(qa_sites_file())
_PIN_REFUSAL = f"injection_judge ({OPENAI_FLAGSHIP})"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PF_QA_TOKEN", raising=False)
    monkeypatch.setattr(chat, "route_framework_logs_to_stderr", lambda: None)


@pytest.fixture
def judge_elsewhere(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "judge_model_id", lambda: OPENAI_FLAGSHIP)


@pytest.fixture
def checked(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    seen: list[str | None] = []

    async def _registered() -> None:
        seen.append(veupathdb_auth_token_ctx.get())

    monkeypatch.setattr(chat, "require_registered_wdk_login", _registered)
    return seen


@pytest.fixture
def unregistered(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _refused() -> None:
        raise WDKLoginRequiredError

    monkeypatch.setattr(chat, "require_registered_wdk_login", _refused)


def _chat(monkeypatch: pytest.MonkeyPatch, argv: list[str]) -> int:
    monkeypatch.setattr("sys.argv", ["chat", *argv])
    with pytest.raises(SystemExit) as exited:
        chat.main()
    code = exited.value.code
    assert isinstance(code, int)
    return code


def _summary() -> EvalRunSummary:
    return EvalRunSummary(
        harness="pydantic-evals",
        provider="default",
        assistant_id="pathfinder",
        ran_at="2026-10-22T00:00:00+00:00",
        cases=[],
    )


@pytest.mark.usefixtures("restored_sites_file", "judge_elsewhere")
@pytest.mark.parametrize(
    "command",
    [
        ["run", "hi"],
        ["respond", "--conversation-id", str(UUID(int=1)), "--accept"],
    ],
)
def test_a_chat_turn_with_a_role_off_the_model_never_starts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    command: list[str],
) -> None:
    started: list[object] = []

    async def _started(args: object) -> int:
        started.append(args)
        return 0

    monkeypatch.setattr(chat, "run_once", _started)
    monkeypatch.setattr(chat, "run_respond", _started)
    turn = tmp_path / "turn"

    code = _chat(
        monkeypatch,
        [
            *command,
            *("--site", "orthomcl", "--sites", _QA, "--run-dir", str(turn)),
            *("--model-all", LUNA),
        ],
    )

    assert code == 2
    assert _PIN_REFUSAL in capsys.readouterr().err
    assert started == []
    assert not turn.exists()


@pytest.mark.usefixtures("restored_sites_file", "judge_elsewhere")
def test_an_eval_run_with_a_role_off_the_model_runs_no_case(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    ran: list[object] = []

    async def _run_corpus(**options: object) -> EvalRunSummary:
        ran.append(options)
        return _summary()

    monkeypatch.setattr(evals, "run_corpus", _run_corpus)

    code = evals.main(["run", "--sites", _QA, "--model", LUNA])

    assert code == 2
    assert _PIN_REFUSAL in capsys.readouterr().err
    assert ran == []


def _sets_the_pin(path: Path) -> bool:
    for node in ast.walk(ast.parse(path.read_text())):
        match node:
            case ast.ImportFrom(module="pathfinder.platform.pinned_model", names=names):
                if any(alias.name == "pin_model" for alias in names):
                    return True
            case ast.ImportFrom(module="pathfinder.platform", names=names):
                if any(alias.name == "pinned_model" for alias in names):
                    return True
            case ast.Import(names=names):
                if any(a.name == "pathfinder.platform.pinned_model" for a in names):
                    return True
            case _:
                pass
    return False


def test_only_the_devtools_set_the_pin() -> None:
    root = Path(pathfinder.__file__).parent
    setters = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if path.relative_to(root).parts[0] != "tests" and _sets_the_pin(path)
    )

    assert setters == ["devtools/run_models.py"]


def test_a_model_the_deployment_does_not_pay_for_is_refused_by_name() -> None:
    own_key = next(e.id for e in get_model_catalog() if not e.deployment_may_pay)

    with (
        pytest.raises(run_models.RunModelError, match=own_key),
        run_models.pin_every_role(own_key),
    ):
        pass


@pytest.mark.usefixtures("input_screening_disabled")
def test_with_screening_off_no_judge_role_is_resolved() -> None:
    with run_models.pin_every_role(LUNA):
        roles = run_models.resolved_roles()

    assert roles == {
        "lead": LUNA,
        "frame": LUNA,
        "execution": LUNA,
        "verification": LUNA,
        "title_generator": LUNA,
        "note_compactor": LUNA,
    }


async def test_the_named_token_is_checked_while_attached(
    monkeypatch: pytest.MonkeyPatch, checked: list[str | None]
) -> None:
    monkeypatch.setenv("PF_QA_TOKEN", _TOKEN)
    args = chat.parse_run_args(
        ["hi", "--site", "orthomcl", "--wdk-token-env", "PF_QA_TOKEN"]
    )

    assert await chat._optional_wdk_token(args) == _TOKEN
    assert checked == [_TOKEN]


@pytest.mark.usefixtures("unregistered")
async def test_a_token_that_names_no_login_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PF_QA_TOKEN", _TOKEN)
    args = chat.parse_run_args(
        ["hi", "--site", "orthomcl", "--wdk-token-env", "PF_QA_TOKEN"]
    )

    with pytest.raises(chat.MissingCredentialsError, match=r"\$PF_QA_TOKEN"):
        await chat._optional_wdk_token(args)


def _case() -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=["build it"],
        site_id="orthomcl",
        assistant_id="pathfinder",
        rationale="pins a thing",
        expected=ExpectedOutcome(builds_strategy=True),
        gates=GatePlan(policy="leave"),
        provenance=CaseProvenance(
            site="orthomcl",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-10-22",
        ),
    )


@pytest.mark.usefixtures("unregistered")
async def test_an_eval_run_on_a_token_that_names_no_login_runs_no_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("PF_QA_TOKEN", _TOKEN)
    ran: list[str] = []

    async def _run_one_case(case: EvalCase, **options: object) -> ObservedOutcome:
        del options
        ran.append(case.name)
        return ObservedOutcome(built_strategy=True)

    async def _site_build(site_id: str) -> str:
        del site_id
        return "70"

    monkeypatch.setattr(eval_runner, "load_corpus", lambda: [_case()])
    monkeypatch.setattr(eval_runner, "site_build", _site_build)
    monkeypatch.setattr(eval_runner, "run_one_case", _run_one_case)

    with pytest.raises(chat.MissingCredentialsError, match=r"\$PF_QA_TOKEN"):
        await eval_runner.run_corpus(
            run_root=tmp_path, wdk_token=EnvToken.read("PF_QA_TOKEN")
        )

    assert ran == []


@asynccontextmanager
async def _no_resource(*_args: object, **_kwargs: object) -> AsyncGenerator[None]:
    yield None


class _Spec:
    def build_graph(self, _saver: object) -> None:
        return None


def _written(root: Path) -> dict[str, str]:
    return {p.name: p.read_text() for p in root.rglob("*") if p.is_file()}


class _NoQueue:
    def open_async(self) -> object:
        return _no_resource()


async def test_the_turn_runs_under_the_named_token_and_no_file_holds_it(
    monkeypatch: pytest.MonkeyPatch, checked: list[str | None], tmp_path: Path
) -> None:
    monkeypatch.setenv("PF_QA_TOKEN", _TOKEN)
    attached: list[str | None] = []

    async def _resolve(_conversation_id: UUID, _assistant: str | None) -> _Spec:
        return _Spec()

    async def _turn(**_kwargs: object) -> None:
        attached.append(veupathdb_auth_token_ctx.get())

    monkeypatch.setattr(chat, "resolve_run_assistant", _resolve)
    monkeypatch.setattr(chat, "lifespan_checkpointer", _no_resource)
    monkeypatch.setattr(chat, "lifespan_memory_store", _no_resource)
    monkeypatch.setattr(chat, "procrastinate_app", _NoQueue())
    monkeypatch.setattr(chat, "run_turn", _turn)
    args = chat.parse_run_args(
        [
            *("hi", "--site", "orthomcl", "--run-dir", str(tmp_path)),
            *("--wdk-token-env", "PF_QA_TOKEN"),
        ]
    )
    conversation_id = uuid4()
    capture = RunCapture(
        conversation_id=conversation_id,
        turn_id=uuid4(),
        run_dir=tmp_path,
        quiet=True,
    )
    message_id = str(uuid4())

    await chat._exec_one(
        args,
        capture,
        ChatRequestBody(
            id=message_id,
            messages=[
                UIMessage(id=message_id, role="user", parts=[TextUIPart(text="hi")])
            ],
            conversation_id=conversation_id,
            site_id="orthomcl",
        ),
        settings_url="postgresql://unused",
        wdk_token=await chat._optional_wdk_token(args),
    )
    capture.flush()
    chat.write_turn_settings(args, assistant_id="pathfinder")

    written = _written(tmp_path)
    assert attached == [_TOKEN]
    assert checked == [_TOKEN]
    assert "turn_settings.json" in written
    assert [name for name, text in written.items() if _TOKEN in text] == []


@pytest.mark.usefixtures("restored_sites_file")
def test_an_eval_run_on_a_named_token_names_its_identity(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PF_QA_TOKEN", _TOKEN)

    async def _run_corpus(**options: object) -> EvalRunSummary:
        del options
        return _summary()

    monkeypatch.setattr(evals, "run_corpus", _run_corpus)

    code = evals.main(["run", "--sites", _QA, "--wdk-token-env", "PF_QA_TOKEN"])

    printed = capsys.readouterr().out.splitlines()
    assert code == 0
    assert printed[0] == "identity: WDK token from $PF_QA_TOKEN"
    assert printed[-2] == "identity: WDK token from $PF_QA_TOKEN"
