"""A case can name a turn that must show the records an earlier turn showed, and
the runner keeps the record ids every turn showed: those its facts list and read,
then those its reply links."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from pathfinder.devtools import eval_runner
from pathfinder.devtools.chat import RunArgs
from pathfinder.devtools.gates import Gate
from pathfinder.domain.record_page import ListedRecord
from pathfinder.domain.turn_facts import ListedFact, SourceFact, TurnFacts
from pathfinder.evals.case import (
    CaseProvenance,
    EvalCase,
    ExpectedOutcome,
    GateEnd,
    GatePlan,
)
from pathfinder.evals.difference import CaseDifference
from pathfinder.evals.scoring import ObservedOutcome, score_case
from pathfinder.evals.store import load_corpus

_SAMPLE = ["ENSMUSG00000037321", "ENSMUSG00000067212", "ENSMUSG00000073411"]


def _listed(*ids: str) -> TurnFacts:
    return TurnFacts(
        listed=[
            ListedFact(
                step_id="step_1",
                step_name="GO term",
                records=[ListedRecord(record_id=i, url=f"https://x/{i}") for i in ids],
            )
        ]
    )


def _checked(*ids: str) -> TurnFacts:
    """The listing, beside two records the turn's check read."""
    read = ["ENSMUSG00000061232", "ENSMUSG00000073409"]
    return _listed(*ids).model_copy(
        update={
            "sources": [SourceFact(url=f"https://x/{i}", record_id=i) for i in read]
        }
    )


def _case(*turns: str, same: dict[int, int]) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=list(turns),
        site_id="hostdb",
        assistant_id="pathfinder",
        rationale="pins a thing",
        expected=ExpectedOutcome(builds_strategy=True, same_records_as=same),
        gates=GatePlan(policy="leave"),
        provenance=CaseProvenance(
            site="hostdb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-10-04",
        ),
    )


def test_a_turn_names_the_records_it_listed_then_read_once_each() -> None:
    facts = _listed(*_SAMPLE[:2]).model_copy(
        update={
            "sources": [
                SourceFact(url="https://x/a", record_id=_SAMPLE[1]),
                SourceFact(url="https://x/b", record_id=_SAMPLE[2]),
                SourceFact(url="https://x/c"),
            ]
        }
    )

    assert facts.record_ids() == _SAMPLE


def test_the_same_records_in_another_order_pass() -> None:
    case = _case("sample five", "that sample again", same={1: 0})
    observed = ObservedOutcome(
        built_strategy=True, turn_record_ids=[_SAMPLE, list(reversed(_SAMPLE))]
    )

    assert score_case(case, observed).differences == []


def test_other_records_are_a_difference_that_names_both_turns() -> None:
    case = _case("sample five", "that sample again", same={1: 0})
    observed = ObservedOutcome(
        built_strategy=True,
        turn_record_ids=[_SAMPLE, [*_SAMPLE[:2], "ENSMUSG00000099999"]],
    )

    assert score_case(case, observed).differences == [
        CaseDifference(
            field="sameRecordsAs[1]",
            expected=", ".join(_SAMPLE),
            actual="ENSMUSG00000037321, ENSMUSG00000067212, ENSMUSG00000099999",
        )
    ]


def test_an_earlier_turn_that_showed_no_record_is_a_difference() -> None:
    case = _case("sample five", "that sample again", same={1: 0})
    observed = ObservedOutcome(built_strategy=True, turn_record_ids=[[], []])

    assert [d.field for d in score_case(case, observed).differences] == [
        "sameRecordsAs[1]"
    ]


def test_a_comparison_names_turns_the_case_has() -> None:
    with pytest.raises(ValidationError, match="names turn 2, and the case has 2"):
        _case("sample five", "that sample again", same={2: 0})


def test_the_hostdb_case_asks_the_fourth_turn_for_the_third_turns_sample() -> None:
    (case,) = [c for c in load_corpus() if c.name == "uat-dry3-d-hostdb"]

    assert case.expected.same_records_as == {3: 2}


def _linked(*ids: str) -> str:
    return "The sample is " + ", ".join(f"[{i}](https://x/{i})" for i in ids) + "."


@pytest.mark.parametrize(
    ("shown", "replies", "kept"),
    [
        pytest.param(
            [_listed(*_SAMPLE), None],
            ["a reply", "a reply"],
            [_SAMPLE, []],
            id="the facts list them",
        ),
        pytest.param(
            [_listed(*_SAMPLE), _listed()],
            [_linked(*_SAMPLE[:2]), _linked(*_SAMPLE)],
            [_SAMPLE, _SAMPLE],
            id="a later reply links the records it did not list",
        ),
        pytest.param(
            [_checked(*_SAMPLE), _listed()],
            [_linked(*_SAMPLE), _linked(*_SAMPLE)],
            [_SAMPLE, _SAMPLE],
            id="a record a check read is no record the turn showed as its answer",
        ),
    ],
)
async def test_the_runner_keeps_the_records_each_turn_showed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    shown: list[TurnFacts | None],
    replies: list[str],
    kept: list[list[str]],
) -> None:
    turns: list[tuple[TurnFacts | None, str]] = list(zip(shown, replies, strict=True))
    observed: list[list[list[str]]] = []

    class _Capture:
        def __init__(self, facts: TurnFacts | None, reply: str) -> None:
            self._facts = facts
            self._reply = reply

        def assistant_text(self) -> str:
            return self._reply

        def turn_facts(self) -> TurnFacts | None:
            return self._facts

        def refused_tools(self) -> list[str]:
            return []

    async def _drive(args: RunArgs) -> tuple[_Capture, Gate]:
        del args
        return _Capture(*turns.pop(0)), Gate(kind="none")

    async def _nothing(conversation_id: UUID) -> None:
        del conversation_id

    async def _step_ids(conversation_id: UUID) -> set[int]:
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
        del conversation_id, step_ids_unchanged, ends_on, refused_tools
        observed.append(turns.record_ids)
        return ObservedOutcome(built_strategy=True)

    async def _forget(user_id: UUID) -> None:
        del user_id

    monkeypatch.setattr(eval_runner, "drive_run", _drive)
    monkeypatch.setattr(eval_runner, "persisted_wdk_step_ids", _step_ids)
    monkeypatch.setattr(eval_runner, "reviewed_requirements", _nothing)
    monkeypatch.setattr(eval_runner, "observe", _observe)
    monkeypatch.setattr(eval_runner, "forget_user", _forget)

    await eval_runner.run_one_case(
        _case("sample five", "that sample again", same={}), run_root=tmp_path
    )

    assert observed == [kept]
