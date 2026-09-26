"""Driving a case: every turn in order on one thread, how it runs, and what it reads."""

from __future__ import annotations

import datetime
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

import pytest

from pathfinder.devtools import eval_runner
from pathfinder.devtools.chat import RespondArgs, RunArgs
from pathfinder.devtools.gates import Gate, GateConsultQuestion, GateOption
from pathfinder.evals.case import (
    CaseProvenance,
    EvalCase,
    ExpectedOutcome,
    GateAnswer,
    GateEnd,
    RecordedCount,
)
from pathfinder.evals.scoring import ObservedOutcome
from pathfinder.evals.store import ATTACHMENTS_DIR


def _case(*turns: str, **fields: object) -> EvalCase:
    case = EvalCase(
        name="a-case",
        turns=list(turns),
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins a thing",
        expected=ExpectedOutcome(builds_strategy=True, step_ids_unchanged=True),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-08-30",
        ),
    )
    return case.model_copy(update=fields)


class _Capture:
    def __init__(self, text: str) -> None:
        self._text = text

    def assistant_text(self) -> str:
        return self._text


class _Installed(NamedTuple):
    """What the stubs recorded, and the stubs themselves for a test to wrap."""

    driven: list[RunArgs]
    read: list[UUID]
    drive: Callable[[RunArgs], Awaitable[tuple[_Capture, Gate]]]
    step_ids: Callable[[UUID], Awaitable[set[int]]]


def _install(
    monkeypatch: pytest.MonkeyPatch,
    step_ids: list[set[int]],
    gate: Gate | None = None,
) -> _Installed:
    driven: list[RunArgs] = []
    read: list[UUID] = []
    remaining = list(step_ids)
    ended = Gate(kind="none") if gate is None else gate

    async def _drive(args: RunArgs) -> tuple[_Capture, Gate]:
        driven.append(args)
        return _Capture(f"reply to {args.prompt}"), ended

    async def _step_ids(conversation_id: UUID) -> set[int]:
        read.append(conversation_id)
        return remaining.pop(0)

    async def _observe(
        conversation_id: UUID,
        reply_text: str,
        *,
        step_ids_unchanged: bool | None,
        ends_on: GateEnd | None,
    ) -> ObservedOutcome:
        del conversation_id
        return ObservedOutcome(
            built_strategy=True,
            reply_text=reply_text,
            step_ids_unchanged=step_ids_unchanged,
            ends_on=ends_on,
        )

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    monkeypatch.setattr(eval_runner, "persisted_wdk_step_ids", _step_ids)
    monkeypatch.setattr(eval_runner, "observe", _observe)
    return _Installed(driven=driven, read=read, drive=_drive, step_ids=_step_ids)


async def test_the_turns_are_driven_in_order_on_one_thread(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100, 200}, {100, 200}])

    await eval_runner.run_one_case(
        _case("build it", "now change one thing"),
        run_root=tmp_path,
    )

    driven = installed.driven
    assert [args.prompt for args in driven] == ["build it", "now change one thing"]
    assert len({args.conversation_id for args in driven}) == 1
    assert [args.run_dir.name for args in driven] == ["turn-1", "turn-2"]


async def test_step_ids_that_survive_the_last_turn_are_reported_unchanged(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [{100, 200}, {100, 200}])

    observed = await eval_runner.run_one_case(
        _case("build it", "swap the organism and keep the rest"),
        run_root=tmp_path,
    )

    assert observed.step_ids_unchanged is True
    assert observed.reply_text == "reply to swap the organism and keep the rest"


async def test_a_rebuild_that_mints_new_step_ids_is_reported_changed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [{100, 200}, {300, 400}])

    observed = await eval_runner.run_one_case(
        _case("build it", "swap the organism and keep the rest"),
        run_root=tmp_path,
    )

    assert observed.step_ids_unchanged is False


async def test_a_thread_that_held_no_step_before_the_last_turn_observes_nothing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set(), {100, 200}])

    observed = await eval_runner.run_one_case(_case("build it"), run_root=tmp_path)

    assert observed.step_ids_unchanged is None


async def test_the_read_happens_before_the_last_turn_and_after_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    order: list[str] = []
    installed = _install(monkeypatch, [{100}, {100}])

    async def _drive(args: RunArgs) -> tuple[_Capture, Gate]:
        order.append(f"turn:{args.prompt}")
        return await installed.drive(args)

    async def _step_ids(conversation_id: UUID) -> set[int]:
        order.append("read")
        return await installed.step_ids(conversation_id)

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    monkeypatch.setattr(eval_runner, "persisted_wdk_step_ids", _step_ids)

    await eval_runner.run_one_case(_case("one", "two"), run_root=tmp_path)

    assert order == ["turn:one", "read", "turn:two", "read"]


async def test_every_turn_runs_at_the_effort_the_run_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100}, {100}])

    await eval_runner.run_one_case(
        _case("build it", "now change one thing"), run_root=tmp_path, effort="high"
    )

    assert [args.effort for args in installed.driven] == ["high", "high"]


async def test_every_turn_runs_at_the_effort_the_case_was_measured_at(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100}, {100}])

    await eval_runner.run_one_case(
        _case("build it", "now change one thing", effort="medium"), run_root=tmp_path
    )

    assert [args.effort for args in installed.driven] == ["medium", "medium"]


async def test_the_effort_the_run_names_wins_over_the_case(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100}])

    await eval_runner.run_one_case(
        _case("build it", effort="medium"), run_root=tmp_path, effort="low"
    )

    assert [args.effort for args in installed.driven] == ["low"]


async def test_a_case_that_stops_leaves_only_the_last_gate_unanswered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100}, {100}])

    await eval_runner.run_one_case(
        _case("build it", "delete a step", gates="stop"), run_root=tmp_path
    )

    assert [args.approve for args in installed.driven] == ["auto", "prompt"]


async def test_a_case_that_does_not_stop_answers_every_gate(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100}, {100}])

    await eval_runner.run_one_case(
        _case("build it", "delete a step"), run_root=tmp_path
    )

    assert [args.approve for args in installed.driven] == ["auto", "auto"]


async def test_each_turn_carries_the_files_the_case_attaches_to_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100}, {100}])

    await eval_runner.run_one_case(
        _case("read this", "and this", attachments={1: ["table.png", "table.pdf"]}),
        run_root=tmp_path,
    )

    assert [args.attachments for args in installed.driven] == [
        [],
        [ATTACHMENTS_DIR / "table.png", ATTACHMENTS_DIR / "table.pdf"],
    ]


async def test_the_run_names_whether_the_worker_executes_the_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100}, {100}, {100}, {100}])

    await eval_runner.run_one_case(_case("one", "two"), run_root=tmp_path)
    await eval_runner.run_one_case(
        _case("one", "two"), run_root=tmp_path, via_worker=True
    )

    assert [args.via_worker for args in installed.driven] == [
        False,
        False,
        True,
        True,
    ]


async def test_no_turn_runs_on_the_scripted_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100}])

    await eval_runner.run_one_case(_case("build it"), run_root=tmp_path)

    assert [args.mock for args in installed.driven] == [False]


async def test_the_gate_the_last_turn_stopped_on_is_observed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(
        monkeypatch,
        [{100}, {100}],
        gate=Gate(kind="approval", tool="delete_step", tool_call_id="call-1"),
    )

    observed = await eval_runner.run_one_case(
        _case("build it", "delete a step", gates="stop"), run_root=tmp_path
    )

    assert observed.ends_on == "approval"


@pytest.mark.parametrize(
    ("gate", "ends_on"),
    [
        (Gate(kind="none"), "none"),
        (Gate(kind="consult", tool="consult_user", tool_call_id="c"), "consult"),
        (Gate(kind="approval", tool="delete_step", tool_call_id="c"), "approval"),
        (Gate(kind="approval", tool="propose_changes", tool_call_id="c"), "proposal"),
        (
            Gate(kind="approval", tool="adopt_separating_strategy", tool_call_id="c"),
            "proposal",
        ),
        (Gate(kind="durable"), None),
    ],
)
def test_a_gate_reads_as_the_card_the_researcher_sees(
    gate: Gate, ends_on: GateEnd | None
) -> None:
    assert eval_runner.gate_end(gate) == ends_on


def _counted(name: str, site: str, count: int) -> EvalCase:
    return _case("build it").model_copy(
        update={
            "name": name,
            "site_id": site,
            "expected": ExpectedOutcome(
                builds_strategy=True,
                root_count=RecordedCount(
                    count=count, build="71", measured_on=datetime.date(2026, 9, 24)
                ),
            ),
        },
    )


async def test_the_corpus_reads_each_site_build_once_and_judges_the_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cases = [
        _counted("uat-s1-plasmodb", "plasmodb", 479),
        _counted("uat-s2-plasmodb", "plasmodb", 116),
        _counted("uat-s2-vectorbase", "vectorbase", 343),
    ]
    produced = {
        "uat-s1-plasmodb": 485,
        "uat-s2-plasmodb": 140,
        "uat-s2-vectorbase": 350,
    }
    builds_read: list[str] = []

    async def _site_build(site_id: str) -> str:
        builds_read.append(site_id)
        return {"plasmodb": "72", "vectorbase": "71"}[site_id]

    async def _run_one_case(
        case: EvalCase,
        *,
        run_root: Path,
        effort: str | None,
        via_worker: bool,
    ) -> ObservedOutcome:
        del run_root, effort, via_worker
        return ObservedOutcome(built_strategy=True, root_count=produced[case.name])

    monkeypatch.setattr(eval_runner, "load_corpus", lambda: cases)
    monkeypatch.setattr(eval_runner, "site_build", _site_build)
    monkeypatch.setattr(eval_runner, "run_one_case", _run_one_case)

    summary = await eval_runner.run_corpus(run_root=tmp_path)

    assert sorted(builds_read) == ["plasmodb", "vectorbase"]
    assert [
        (case.name, case.verdict, case.observed_count, case.differences)
        for case in summary.cases
    ] == [
        ("uat-s1-plasmodb", "pass", 485, []),
        ("uat-s2-plasmodb", "re-measure", 140, []),
        ("uat-s2-vectorbase", "fail", 350, []),
    ]
    assert [
        (case.count_drift.expected, case.count_drift.actual)
        for case in summary.cases
        if case.count_drift is not None
    ] == [
        ("479 (build 71)", "485 (build 72)"),
        ("116 (build 71)", "140 (build 72)"),
        ("343 (build 71)", "350 (build 71)"),
    ]


_RUN_CARD = Gate(kind="approval", tool="separate_controls", tool_call_id="run")
_OFFER_CARD = Gate(
    kind="approval", tool="adopt_separating_strategy", tool_call_id="offer"
)
_NO = GateAnswer(accept=False, comment="Too broad for a vaccine screen.")


def _answering(
    monkeypatch: pytest.MonkeyPatch, raised: list[Gate | None]
) -> list[RespondArgs]:
    """Each answer moves the turn to the next gate *raised* lists; None is no card."""
    answered: list[RespondArgs] = []
    remaining = list(raised)

    async def _respond(args: RespondArgs) -> tuple[_Capture, Gate] | None:
        answered.append(args)
        gate = remaining.pop(0)
        return None if gate is None else (_Capture(f"answered {len(answered)}"), gate)

    monkeypatch.setattr(eval_runner, "drive_respond", _respond)
    return answered


async def test_explicit_answers_answer_the_gates_in_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [set(), set()])
    raised = [Gate(kind="none"), _RUN_CARD]

    async def _drive(args: RunArgs) -> tuple[_Capture, Gate]:
        capture, _ = await installed.drive(args)
        return capture, raised.pop(0)

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    answered = _answering(monkeypatch, [_OFFER_CARD, Gate(kind="none")])

    observed = await eval_runner.run_one_case(
        _case("separate these", "yes, run it", gates=[GateAnswer(accept=True), _NO]),
        run_root=tmp_path,
        via_worker=True,
    )

    assert [args.approve for args in installed.driven] == ["prompt", "prompt"]
    assert [(a.accept, a.deny, a.reason) for a in answered] == [
        (True, False, None),
        (False, True, "Too broad for a vaccine screen."),
    ]
    assert {
        (a.conversation_id, a.run_dir.name, a.via_worker, a.site) for a in answered
    } == {(installed.driven[0].conversation_id, "turn-2", True, "plasmodb")}
    assert (observed.ends_on, observed.reply_text) == ("none", "answered 2")


async def test_a_gate_past_the_last_answer_is_left_unanswered(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set()], gate=_RUN_CARD)
    answered = _answering(monkeypatch, [_OFFER_CARD])

    observed = await eval_runner.run_one_case(
        _case("separate these", gates=[GateAnswer(accept=True)]), run_root=tmp_path
    )

    assert (len(answered), observed.ends_on) == (1, "proposal")


_QUESTIONS = Gate(
    kind="consult",
    tool="consult_user",
    tool_call_id="q",
    consult_questions=[
        GateConsultQuestion(
            id="route",
            prompt="Where should the transform run?",
            options=[
                GateOption(label="On the VEuPathDB portal"),
                GateOption(label="Stay on PlasmoDB", recommended=True),
            ],
        ),
        GateConsultQuestion(
            id="strictness",
            prompt="How strict?",
            options=[
                GateOption(label="Loose"),
                GateOption(label="Strict", recommended=True),
            ],
        ),
        GateConsultQuestion(id="why", prompt="Anything else?", kind="free_text"),
    ],
)


async def test_a_card_answer_is_not_given_to_a_question_card(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set()], gate=_QUESTIONS)
    answered = _answering(monkeypatch, [])

    observed = await eval_runner.run_one_case(
        _case("find drug targets", gates=[GateAnswer(accept=True)]), run_root=tmp_path
    )

    assert (answered, observed.ends_on) == ([], "consult")


async def test_a_question_answer_is_not_given_to_an_approval_card(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set()], gate=_RUN_CARD)
    answered = _answering(monkeypatch, [])

    observed = await eval_runner.run_one_case(
        _case("separate these", gates=[GateAnswer(picks=["portal"])]),
        run_root=tmp_path,
    )

    assert (answered, observed.ends_on) == ([], "approval")


async def test_a_question_card_takes_the_picked_options_else_the_recommended(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set()], gate=_QUESTIONS)
    answered = _answering(monkeypatch, [Gate(kind="none")])

    observed = await eval_runner.run_one_case(
        _case("carry these", gates=[GateAnswer(picks=["portal"])]), run_root=tmp_path
    )

    assert [(a.answers, a.accept, a.deny) for a in answered] == [
        (
            ["route=On the VEuPathDB portal", "strictness=Strict", "why=portal"],
            False,
            False,
        ),
    ]
    assert observed.ends_on == "none"


async def test_an_answer_due_with_no_card_pending_ends_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set()], gate=_RUN_CARD)
    answered = _answering(monkeypatch, [None])

    observed = await eval_runner.run_one_case(
        _case("separate these", gates=[GateAnswer(accept=True), _NO]),
        run_root=tmp_path,
    )

    assert (len(answered), observed.ends_on) == (1, "none")


async def test_a_turn_can_open_a_new_conversation_and_is_read_there(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100}, {100}])
    observed_on: list[UUID] = []

    async def _observe(
        conversation_id: UUID,
        reply_text: str,
        *,
        step_ids_unchanged: bool | None,
        ends_on: GateEnd | None,
    ) -> ObservedOutcome:
        observed_on.append(conversation_id)
        return ObservedOutcome(
            built_strategy=False,
            reply_text=reply_text,
            step_ids_unchanged=step_ids_unchanged,
            ends_on=ends_on,
        )

    monkeypatch.setattr(eval_runner, "observe", _observe)

    await eval_runner.run_one_case(
        _case("remember this", "what do I prefer?", new_conversation_before=[1]),
        run_root=tmp_path,
    )

    first, second = (args.conversation_id for args in installed.driven)
    assert (first != second, observed_on, installed.read) == (
        True,
        [second],
        [second, second],
    )
