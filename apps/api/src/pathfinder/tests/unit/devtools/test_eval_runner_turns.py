"""Driving a case: every turn in order on one thread, how it runs, and what it reads."""

from __future__ import annotations

import datetime
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import NamedTuple
from uuid import UUID

import httpx
import pytest

from pathfinder.ai.conversation.gene_list_marker import (
    ParsedGeneList,
    parse_gene_list_marker,
)
from pathfinder.devtools import eval_runner, evals
from pathfinder.devtools.chat import LoginUnansweredError, RespondArgs, RunArgs
from pathfinder.devtools.gates import Gate, GateConsultQuestion, GateOption
from pathfinder.domain.turn_facts import ParameterFact, StepFact, TurnFacts
from pathfinder.evals import store
from pathfinder.evals.case import (
    CaseProvenance,
    EvalCase,
    ExpectedOutcome,
    GateAnswer,
    GateEnd,
    GatePlan,
    RecordedCount,
)
from pathfinder.evals.scoring import ObservedOutcome, RequirementCounts, score_case
from pathfinder.evals.store import ATTACHMENTS_DIR


def _case(*turns: str, **fields: object) -> EvalCase:
    case = EvalCase(
        name="a-case",
        turns=list(turns),
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins a thing",
        expected=ExpectedOutcome(builds_strategy=True, step_ids_unchanged=True),
        gates=GatePlan(policy="leave"),
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
    def __init__(
        self,
        text: str,
        refused: tuple[str, ...] = (),
        facts: TurnFacts | None = None,
    ) -> None:
        self._text = text
        self._refused = list(refused)
        self._facts = facts

    def assistant_text(self) -> str:
        return self._text

    def turn_facts(self) -> TurnFacts | None:
        return self._facts

    def refused_tools(self) -> list[str]:
        return self._refused


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
    reviews: list[RequirementCounts | None] | None = None,
) -> _Installed:
    driven: list[RunArgs] = []
    read: list[UUID] = []
    remaining = list(step_ids)
    reviewed = list(reviews or [])
    ended = Gate(kind="none") if gate is None else gate

    async def _drive(args: RunArgs) -> tuple[_Capture, Gate]:
        driven.append(args)
        return _Capture(f"reply to {args.prompt}"), ended

    async def _step_ids(conversation_id: UUID) -> set[int]:
        read.append(conversation_id)
        return remaining.pop(0)

    async def _reviewed(conversation_id: UUID) -> RequirementCounts | None:
        del conversation_id
        return reviewed.pop(0) if reviewed else None

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
            turn_replies=turns.replies,
            requirements=turns.requirements,
            step_ids_unchanged=step_ids_unchanged,
            ends_on=ends_on,
            refused_tools=refused_tools,
        )

    async def _forget(user_id: UUID) -> None:
        del user_id

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    monkeypatch.setattr(eval_runner, "persisted_wdk_step_ids", _step_ids)
    monkeypatch.setattr(eval_runner, "observe", _observe)
    monkeypatch.setattr(eval_runner, "reviewed_requirements", _reviewed)
    monkeypatch.setattr(eval_runner, "forget_user", _forget)
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


_DELETE_CARD = Gate(kind="approval", tool="delete_step", tool_call_id="del")


def _leave(*answers: GateAnswer) -> GatePlan:
    return GatePlan(policy="leave", answers=list(answers))


async def test_a_case_that_stops_answers_every_card_but_the_last_turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100}, {100}], gate=_DELETE_CARD)
    answered = _answering(monkeypatch, [Gate(kind="none")])

    observed = await eval_runner.run_one_case(
        _case("build it", "delete a step", gates=GatePlan(policy="stop")),
        run_root=tmp_path,
    )

    assert (
        [args.approve for args in installed.driven],
        [(a.accept, a.run_dir.parent.name) for a in answered],
        observed.ends_on,
    ) == (["prompt", "prompt"], [(True, "turn-1")], "approval")


async def test_a_case_that_does_not_stop_answers_every_card(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [{100}, {100}], gate=_DELETE_CARD)
    answered = _answering(monkeypatch, [Gate(kind="none"), Gate(kind="none")])

    await eval_runner.run_one_case(
        _case("build it", "delete a step", gates=GatePlan(policy="auto")),
        run_root=tmp_path,
    )

    assert [(a.accept, a.run_dir.parent.name, a.run_dir.name) for a in answered] == [
        (True, "turn-1", "answer-1"),
        (True, "turn-2", "answer-1"),
    ]


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

    _answering(monkeypatch, [Gate(kind="none")])

    observed = await eval_runner.run_one_case(
        _case("build it", "delete a step", gates=GatePlan(policy="stop")),
        run_root=tmp_path,
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


async def test_a_case_whose_site_login_did_not_answer_is_not_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cases = [
        _counted("uat-s1-plasmodb", "plasmodb", 479),
        _counted("uat-s1-cryptodb", "cryptodb", 12),
        _counted("uat-s2-plasmodb", "plasmodb", 116),
    ]

    async def _site_build(site_id: str) -> str:
        del site_id
        return "71"

    async def _run_one_case(
        case: EvalCase,
        *,
        run_root: Path,
        effort: str | None,
        via_worker: bool,
    ) -> ObservedOutcome:
        del run_root, effort, via_worker
        if case.site_id == "cryptodb":
            unanswered = httpx.ConnectTimeout("no answer")
            raise LoginUnansweredError(case.site_id, unanswered)
        if case.name == "uat-s2-plasmodb":
            msg = "the turn broke"
            raise RuntimeError(msg)
        return ObservedOutcome(built_strategy=True, root_count=479)

    monkeypatch.setattr(eval_runner, "load_corpus", lambda: cases)
    monkeypatch.setattr(eval_runner, "site_build", _site_build)
    monkeypatch.setattr(eval_runner, "run_one_case", _run_one_case)

    summary = await eval_runner.run_corpus(run_root=tmp_path)

    assert [(case.name, case.verdict, case.error) for case in summary.cases] == [
        (
            "uat-s1-cryptodb",
            "not-run",
            "cryptodb login did not answer (connect timeout)",
        ),
        ("uat-s1-plasmodb", "pass", ""),
        ("uat-s2-plasmodb", "fail", "RuntimeError: the turn broke"),
    ]
    counted = (summary.passed, summary.failed, summary.errored, summary.not_run)
    assert counted == (1, 0, 1, 1)
    assert summary.pass_rate == 0.5


_RUN_CARD = Gate(kind="approval", tool="separate_controls", tool_call_id="run")
_OFFER_CARD = Gate(
    kind="approval", tool="adopt_separating_strategy", tool_call_id="offer"
)
_YES_TO_THE_RUN = GateAnswer(card="separate_controls", turn=1)
_NO_TO_THE_OFFER = GateAnswer(
    card="adopt_separating_strategy",
    turn=1,
    accept=False,
    comment="Too broad for a vaccine screen.",
)


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
        _case(
            "separate these",
            "yes, run it",
            gates=_leave(_YES_TO_THE_RUN, _NO_TO_THE_OFFER),
        ),
        run_root=tmp_path,
        via_worker=True,
    )

    assert [args.approve for args in installed.driven] == ["prompt", "prompt"]
    assert [(a.accept, a.deny, a.reason) for a in answered] == [
        (True, False, None),
        (False, True, "Too broad for a vaccine screen."),
    ]
    assert [
        (a.conversation_id, a.run_dir.parent.name, a.run_dir.name, a.via_worker)
        for a in answered
    ] == [
        (installed.driven[0].conversation_id, "turn-2", "answer-1", True),
        (installed.driven[0].conversation_id, "turn-2", "answer-2", True),
    ]
    assert (observed.ends_on, observed.reply_text) == ("none", "answered 2")
    assert observed.turn_replies == ["reply to separate these", "answered 2"]


async def test_the_refused_tools_are_read_from_every_run_and_every_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [set(), set()])
    raised = [Gate(kind="none"), _RUN_CARD]
    refused_by_turn = [("classify_user_intent",), ("read_gene_record",)]

    async def _drive(args: RunArgs) -> tuple[_Capture, Gate]:
        await installed.drive(args)
        return _Capture("ran", refused_by_turn.pop(0)), raised.pop(0)

    async def _respond(args: RespondArgs) -> tuple[_Capture, Gate] | None:
        del args
        return _Capture("answered", ("get_strategy", "get_strategy")), Gate(kind="none")

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    monkeypatch.setattr(eval_runner, "drive_respond", _respond)

    observed = await eval_runner.run_one_case(
        _case("separate these", "yes, run it", gates=_leave(_YES_TO_THE_RUN)),
        run_root=tmp_path,
    )

    assert observed.refused_tools == [
        "classify_user_intent",
        "read_gene_record",
        "get_strategy",
        "get_strategy",
    ]


async def test_a_card_no_answer_names_is_left_under_the_leave_policy(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set()], gate=_RUN_CARD)
    answered = _answering(monkeypatch, [_OFFER_CARD])

    observed = await eval_runner.run_one_case(
        _case(
            "separate these",
            gates=_leave(GateAnswer(card="separate_controls", turn=0)),
        ),
        run_root=tmp_path,
    )

    assert (len(answered), observed.ends_on) == (1, "proposal")


async def test_a_case_that_must_not_build_declines_the_offer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set()], gate=_OFFER_CARD)
    answered = _answering(monkeypatch, [Gate(kind="none")])

    await eval_runner.run_one_case(
        _case(
            "I'm investigating virulence factors.",
            expected=ExpectedOutcome(builds_strategy=False),
            gates=GatePlan(policy="decline-offers"),
        ),
        run_root=tmp_path,
    )

    assert [(a.accept, a.deny) for a in answered] == [(False, True)]


async def test_an_answer_for_a_card_never_raised_blocks_no_later_answer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [set(), set()])
    raised = [Gate(kind="none"), _DELETE_CARD]

    async def _drive(args: RunArgs) -> tuple[_Capture, Gate]:
        capture, _ = await installed.drive(args)
        return capture, raised.pop(0)

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    answered = _answering(monkeypatch, [Gate(kind="none")])

    observed = await eval_runner.run_one_case(
        _case(
            "Find kinases.",
            "Delete the text step.",
            gates=_leave(
                GateAnswer(card="consult_user", turn=0, picks=["kinase"]),
                GateAnswer(card="delete_step", turn=1),
            ),
        ),
        run_root=tmp_path,
    )

    assert ([a.run_dir.parent.name for a in answered], observed.ends_on) == (
        ["turn-2"],
        "none",
    )


async def test_an_answer_is_given_only_to_the_card_of_the_turn_it_names(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set(), set()], gate=_DELETE_CARD)
    answered = _answering(monkeypatch, [Gate(kind="none")])

    await eval_runner.run_one_case(
        _case(
            "Delete the text step.",
            "Delete the GO step.",
            gates=_leave(GateAnswer(card="delete_step", turn=1)),
        ),
        run_root=tmp_path,
    )

    assert [a.run_dir.parent.name for a in answered] == ["turn-2"]


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
        _case(
            "find drug targets",
            gates=_leave(GateAnswer(card="delete_step", turn=0)),
        ),
        run_root=tmp_path,
    )

    assert (answered, observed.ends_on) == ([], "consult")


async def test_a_question_answer_is_not_given_to_an_approval_card(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set()], gate=_RUN_CARD)
    answered = _answering(monkeypatch, [])

    observed = await eval_runner.run_one_case(
        _case(
            "separate these",
            gates=_leave(GateAnswer(card="consult_user", turn=0, picks=["portal"])),
        ),
        run_root=tmp_path,
    )

    assert (answered, observed.ends_on) == ([], "approval")


async def test_a_question_card_takes_the_picked_options_else_the_recommended(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(monkeypatch, [set()], gate=_QUESTIONS)
    answered = _answering(monkeypatch, [Gate(kind="none")])

    observed = await eval_runner.run_one_case(
        _case(
            "carry these",
            gates=_leave(GateAnswer(card="consult_user", turn=0, picks=["portal"])),
        ),
        run_root=tmp_path,
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
        _case(
            "separate these",
            gates=_leave(
                GateAnswer(card="separate_controls", turn=0),
                GateAnswer(card="separate_controls", turn=0, accept=False),
            ),
        ),
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
        turns: eval_runner.TurnsShown,
        *,
        step_ids_unchanged: bool | None,
        ends_on: GateEnd | None,
        refused_tools: list[str],
    ) -> ObservedOutcome:
        observed_on.append(conversation_id)
        return ObservedOutcome(
            built_strategy=False,
            reply_text=turns.replies[-1],
            step_ids_unchanged=step_ids_unchanged,
            ends_on=ends_on,
            refused_tools=refused_tools,
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


def test_each_verdict_is_printed_as_it_is_known_before_the_summary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cases = [
        _counted("uat-s1-plasmodb", "plasmodb", 479),
        _counted("uat-s2-plasmodb", "plasmodb", 116),
    ]
    produced = {"uat-s1-plasmodb": 479, "uat-s2-plasmodb": 140}
    printed_before_each_case: list[str] = []

    async def _site_build(site_id: str) -> str:
        del site_id
        return "71"

    async def _run_one_case(
        case: EvalCase,
        *,
        run_root: Path,
        effort: str | None,
        via_worker: bool,
    ) -> ObservedOutcome:
        del run_root, effort, via_worker
        printed_before_each_case.append(capsys.readouterr().out)
        return ObservedOutcome(built_strategy=True, root_count=produced[case.name])

    monkeypatch.setattr(eval_runner, "load_corpus", lambda: cases)
    monkeypatch.setattr(eval_runner, "site_build", _site_build)
    monkeypatch.setattr(eval_runner, "run_one_case", _run_one_case)
    monkeypatch.setattr(evals, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(evals, "route_framework_logs_to_stderr", lambda: None)

    assert evals.main(["run"]) == 0

    after = capsys.readouterr().out.splitlines()
    first = printed_before_each_case[1].split()
    second, _, difference = after[0].partition("  ")
    assert (printed_before_each_case[0], first[:2], first[3:]) == (
        "",
        ["pass", "uat-s1-plasmodb"],
        ["count=479", "assumed=-", "refusals=0", "-"],
    )
    assert (second.split()[:2], second.split()[3:], difference) == (
        ["fail", "uat-s2-plasmodb"],
        ["count=140", "assumed=-", "refusals=0"],
        "rootCount: expected '116 (build 71)', got '140 (build 71)'",
    )
    assert (after[1].split()[:2], after[-1].split()[:6]) == (
        ["PASS", "uat-s1-plasmodb"],
        ["---", "1/2", "passed", "(re-measure", "0,", "failed"],
    )
    assert "errored 0, not run 0) refusals=0 assumed=- harness=" in after[-1]


def test_a_passing_case_prints_its_refusals_on_every_line(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A retry refusal and a guard refusal both show on a case that passes."""
    cases = [_counted("uat-s1-plasmodb", "plasmodb", 479)]
    out = tmp_path / "summary.json"

    async def _site_build(site_id: str) -> str:
        del site_id
        return "71"

    async def _run_one_case(
        case: EvalCase,
        *,
        run_root: Path,
        effort: str | None,
        via_worker: bool,
    ) -> ObservedOutcome:
        del case, run_root, effort, via_worker
        return ObservedOutcome(
            built_strategy=True,
            root_count=479,
            refused_tools=["classify_user_intent", "read_gene_record"],
            assumed=0,
        )

    monkeypatch.setattr(eval_runner, "load_corpus", lambda: cases)
    monkeypatch.setattr(eval_runner, "site_build", _site_build)
    monkeypatch.setattr(eval_runner, "run_one_case", _run_one_case)
    monkeypatch.setattr(evals, "RUN_ROOT", tmp_path)
    monkeypatch.setattr(evals, "route_framework_logs_to_stderr", lambda: None)

    assert evals.main(["run", "--out", str(out)]) == 0

    lines = capsys.readouterr().out.splitlines()
    progress, _, first = lines[0].partition("  ")
    listed = lines[1].split("  ")
    assert (progress.split()[3:], first) == (
        [
            "count=479",
            "assumed=0",
            "refusals=2",
            "(classify_user_intent,",
            "read_gene_record)",
        ],
        "-",
    )
    assert (listed[0], listed[1], listed[3:]) == (
        "PASS",
        "uat-s1-plasmodb",
        [
            "count 479",
            "assumed=0",
            "refusals=2 (classify_user_intent, read_gene_record)",
        ],
    )
    assert "errored 0, not run 0) refusals=2 assumed=0 harness=" in lines[-2]
    payload = json.loads(out.read_text())
    assert (payload["refusals"], payload["cases"][0]["refusedTools"]) == (
        2,
        ["classify_user_intent", "read_gene_record"],
    )
    assert (payload["assumed"], payload["cases"][0]["assumed"]) == (0, 0)


async def test_a_gene_list_file_reaches_the_turn_as_the_composer_writes_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    files = tmp_path / "files"
    files.mkdir()
    (files / "controls.csv").write_text(
        "geneId,product\n"
        "PF3D7_0709000,CRT\n"
        "PF3D7_1133400,AMA1\n"
        "PF3D7_0102600,unspecified\n"
        "PF3D7_0709000,CRT\n"
    )
    (files / "table.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr(store, "ATTACHMENTS_DIR", files)
    installed = _install(monkeypatch, [set()])

    await eval_runner.run_one_case(
        _case(
            "Use these genes as my positive controls.",
            attachments={0: ["controls.csv", "table.png"]},
        ),
        run_root=tmp_path,
    )

    (driven,) = installed.driven
    listed = parse_gene_list_marker(driven.prompt)
    assert driven.prompt == (
        "Use these genes as my positive controls.\n\n"
        "Attached gene-ID list from controls.csv: "
        "PF3D7_0709000, PF3D7_1133400, PF3D7_0102600"
    )
    assert (listed, driven.attachments) == (
        ParsedGeneList(
            file_name="controls.csv",
            gene_ids=["PF3D7_0709000", "PF3D7_1133400", "PF3D7_0102600"],
        ),
        [files / "table.png"],
    )


async def test_a_gene_list_file_with_no_ids_says_so(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "empty.txt").write_text("gene_id\n\n")
    monkeypatch.setattr(store, "ATTACHMENTS_DIR", tmp_path)
    installed = _install(monkeypatch, [set()])

    await eval_runner.run_one_case(
        _case("Use these.", attachments={0: ["empty.txt"]}), run_root=tmp_path
    )

    assert [(a.prompt, a.attachments) for a in installed.driven] == [
        (
            "Use these.\n\nAttached file empty.txt contained no recognizable gene IDs.",
            [],
        ),
    ]


async def test_a_turn_is_observed_as_its_reply_and_the_facts_part_beside_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    installed = _install(monkeypatch, [{100}])
    shown = TurnFacts(steps=[StepFact(step_id="c1", display_name="GO Term", count=74)])
    observed: list[eval_runner.TurnsShown] = []

    async def _drive(args: RunArgs) -> tuple[_Capture, Gate]:
        await installed.drive(args)
        return _Capture("The count is shown beside this reply.", facts=shown), Gate(
            kind="none"
        )

    async def _observe(
        conversation_id: UUID,
        turns: eval_runner.TurnsShown,
        *,
        step_ids_unchanged: bool | None,
        ends_on: GateEnd | None,
        refused_tools: list[str],
    ) -> ObservedOutcome:
        del conversation_id, step_ids_unchanged
        observed.append(turns)
        return ObservedOutcome(
            built_strategy=True, ends_on=ends_on, refused_tools=refused_tools
        )

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    monkeypatch.setattr(eval_runner, "observe", _observe)

    await eval_runner.run_one_case(_case("build it"), run_root=tmp_path)

    assert observed == [
        eval_runner.TurnsShown(
            replies=["The count is shown beside this reply."],
            facts=["Strategy\nGO Term: 74 genes"],
            last_facts=shown,
            record_ids=[[]],
        )
    ]


def test_the_facts_text_shows_who_set_each_value() -> None:
    """A case reads each value beside the source label the facts part shows."""
    facts = TurnFacts(
        steps=[
            StepFact(
                step_id="step_27087579",
                display_name="Text (product name, notes, etc.)",
                count=3308,
                parameters=[
                    ParameterFact(
                        name="text_search_organism",
                        display_name="Organism",
                        value="Giardia muris strain Roberts-Thomson",
                        source="stated",
                    ),
                    ParameterFact(
                        name="text_fields",
                        display_name="Fields",
                        value="product, Notes",
                        label="Product description, Notes from annotators",
                        source="chosen",
                    ),
                ],
            )
        ]
    )

    assert eval_runner.facts_text(facts).splitlines() == [
        "Strategy",
        "Text (product name, notes, etc.): 3,308 genes",
        "  Organism: Giardia muris strain Roberts-Thomson (stated)",
        "  Fields: product, Notes (Product description, Notes from annotators) (chosen)",
    ]


async def test_the_latest_review_stands_through_a_turn_that_ran_no_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    reviewed = RequirementCounts(met=2, unmet=0, unexpressed=0)
    _install(monkeypatch, [{100}, {100}], reviews=[reviewed, None])
    case = _case(
        "build it",
        "summarize the session",
        expected=ExpectedOutcome(builds_strategy=True, unexpressed_requirements=0),
    )

    observed = await eval_runner.run_one_case(case, run_root=tmp_path)

    assert observed.requirements == reviewed
    assert score_case(case, observed).differences == []


async def test_a_new_conversation_drops_the_review_of_the_last_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _install(
        monkeypatch,
        [{100}, {100}],
        reviews=[RequirementCounts(met=1), None],
    )
    case = _case("build it", "build again", new_conversation_before=[1])

    observed = await eval_runner.run_one_case(case, run_root=tmp_path)

    assert [observed.requirements] == [None]
