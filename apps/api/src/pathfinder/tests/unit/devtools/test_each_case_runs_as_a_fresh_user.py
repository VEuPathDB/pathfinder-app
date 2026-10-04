"""Each corpus case runs as a user of its own, and that user's memories go when
the case ends."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from pathfinder.devtools import eval_runner
from pathfinder.devtools.chat import DEV_USER_ID, RespondArgs, RunArgs
from pathfinder.devtools.gates import Gate
from pathfinder.evals.case import (
    CaseProvenance,
    EvalCase,
    ExpectedOutcome,
    GateAnswer,
    GateEnd,
    GatePlan,
)
from pathfinder.evals.scoring import ObservedOutcome

_RUN_CARD = Gate(kind="approval", tool="separate_controls", tool_call_id="run")


def _case(*turns: str, gates: GatePlan | None = None) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=list(turns),
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins a thing",
        expected=ExpectedOutcome(builds_strategy=True),
        gates=gates or GatePlan(policy="leave"),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-10-04",
        ),
    )


class _Capture:
    def assistant_text(self) -> str:
        return "a reply"

    def turn_facts(self) -> None:
        return None

    def refused_tools(self) -> list[str]:
        return []


class _Recorded:
    def __init__(self) -> None:
        self.driven: list[RunArgs] = []
        self.answered: list[RespondArgs] = []
        self.forgotten: list[UUID] = []


def _install(
    monkeypatch: pytest.MonkeyPatch, gates: list[Gate] | None = None
) -> _Recorded:
    recorded = _Recorded()
    raised = list(gates or [])

    async def _drive(args: RunArgs) -> tuple[_Capture, Gate]:
        recorded.driven.append(args)
        return _Capture(), raised.pop(0) if raised else Gate(kind="none")

    async def _respond(args: RespondArgs) -> tuple[_Capture, Gate]:
        recorded.answered.append(args)
        return _Capture(), Gate(kind="none")

    async def _step_ids(conversation_id: UUID) -> set[int]:
        del conversation_id
        return set()

    async def _reviewed(conversation_id: UUID) -> None:
        del conversation_id

    async def _observe(
        conversation_id: UUID,
        turns: eval_runner.TurnsShown,
        *,
        step_ids_unchanged: bool | None,
        ends_on: GateEnd | None,
        refused_tools: list[str],
    ) -> ObservedOutcome:
        del conversation_id
        return ObservedOutcome(
            built_strategy=True,
            reply_text=turns.replies[-1],
            step_ids_unchanged=step_ids_unchanged,
            ends_on=ends_on,
            refused_tools=refused_tools,
        )

    async def _forget(user_id: UUID) -> None:
        recorded.forgotten.append(user_id)

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    monkeypatch.setattr(eval_runner, "drive_respond", _respond)
    monkeypatch.setattr(eval_runner, "persisted_wdk_step_ids", _step_ids)
    monkeypatch.setattr(eval_runner, "reviewed_requirements", _reviewed)
    monkeypatch.setattr(eval_runner, "observe", _observe)
    monkeypatch.setattr(eval_runner, "forget_user", _forget)
    return recorded


def test_the_command_line_runs_as_the_debugger_user(tmp_path: Path) -> None:
    args = RunArgs(
        prompt="hi", site="plasmodb", conversation_id=uuid4(), run_dir=tmp_path
    )

    assert args.user_id == DEV_USER_ID


async def test_every_turn_of_a_case_runs_as_one_user_of_its_own(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorded = _install(monkeypatch)

    await eval_runner.run_one_case(_case("build it", "change it"), run_root=tmp_path)

    users = {args.user_id for args in recorded.driven}
    assert len(users) == 1
    assert users != {DEV_USER_ID}


async def test_two_cases_run_as_two_users(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorded = _install(monkeypatch)

    await eval_runner.run_one_case(_case("build it"), run_root=tmp_path)
    await eval_runner.run_one_case(_case("build it"), run_root=tmp_path)

    first, second = (args.user_id for args in recorded.driven)
    assert first != second


async def test_an_answer_to_a_card_runs_as_the_case_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorded = _install(monkeypatch, [_RUN_CARD])
    yes = GateAnswer(card="separate_controls", turn=0)

    await eval_runner.run_one_case(
        _case("separate these", gates=GatePlan(policy="leave", answers=[yes])),
        run_root=tmp_path,
    )

    assert [args.user_id for args in recorded.answered] == [recorded.driven[0].user_id]


async def test_the_case_user_is_forgotten_when_the_case_ends(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorded = _install(monkeypatch)

    await eval_runner.run_one_case(_case("build it", "change it"), run_root=tmp_path)

    assert recorded.forgotten == [recorded.driven[0].user_id]


async def test_a_case_that_raises_still_forgets_its_user(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    recorded = _install(monkeypatch)

    async def _fail(args: RunArgs) -> tuple[_Capture, Gate]:
        recorded.driven.append(args)
        msg = "the site did not answer"
        raise RuntimeError(msg)

    monkeypatch.setattr(eval_runner, "drive_run", _fail)

    with pytest.raises(RuntimeError, match="the site did not answer"):
        await eval_runner.run_one_case(_case("build it"), run_root=tmp_path)

    assert recorded.forgotten == [recorded.driven[0].user_id]
