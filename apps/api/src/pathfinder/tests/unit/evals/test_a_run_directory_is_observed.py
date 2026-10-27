"""A chat-debugger run directory, with no database, is read as the scorer's observation."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest
from veupathdb.domain.parameters import PhyleticTree, TaxonEntry

from pathfinder.devtools.gates import Gate, GateConsultQuestion, GateOption
from pathfinder.evals.case import EvalCase
from pathfinder.evals.difference import CaseDifference
from pathfinder.evals.distance import COMBINE_LABEL, ComparisonNode
from pathfinder.evals.run_directory import (
    UnobservedFieldError,
    observed_from_run_directory,
    score_run_directory,
)
from pathfinder.evals.scoring import score_case
from pathfinder.evals.store import load_case

_RUN = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "evals"
    / "run_directory"
    / "orthomcl-one-protein-in-each-cryptosporidium-genome"
)
_CRYPTO = [
    "cand",
    "cbov",
    "choi",
    "chot",
    "chom",
    "chod",
    "cmel",
    "cmtu",
    "cmur",
    "cpia",
    "cpib",
    "cpar",
    "crya",
    "cser",
    "cspi",
    "cscp",
    "ctyz",
    "cubi",
]


def _crypto_tree() -> PhyleticTree:
    return PhyleticTree.from_taxa(
        [
            TaxonEntry(
                id="CRYS",
                parent_id=None,
                code="CRYS",
                label="Cryptosporidium",
                clade=True,
            ),
            *(
                TaxonEntry(
                    id=code, parent_id="CRYS", code=code, label=code, clade=False
                )
                for code in _CRYPTO
            ),
        ]
    )


def test_the_baseline_run_is_observed_from_its_files() -> None:
    observed = observed_from_run_directory(_RUN)

    assert (
        observed.built_strategy,
        observed.structure,
        observed.record_type,
        observed.step_count,
        observed.root_count,
        observed.ends_on,
        observed.verified,
        observed.consult_options,
    ) == (True, "GroupsByPhyleticPattern", "group", 1, 1736, "none", False, [])
    assert "1,736" in observed.reply_text
    assert observed.turn_replies == [observed.reply_text]
    assert "Phyletic Pattern: 1,736 groups" in observed.facts_text


def test_the_baseline_expression_grades_equal_to_the_measured_one() -> None:
    case = load_case("orthomcl-one-protein-in-each-cryptosporidium-genome")

    score = score_case(case, observed_from_run_directory(_RUN), _crypto_tree())

    assert [
        d.field for d in score.differences if d.field.startswith("expressions")
    ] == []


_STRATEGY = "28-GET-214645000.json"
_STEP = "227284110"
_QUESTION = Gate(
    kind="consult",
    tool="consult_user",
    tool_call_id="c",
    consult_questions=[
        GateConsultQuestion(
            id="reading",
            prompt="Which reading?",
            options=[GateOption(label="Every genome", recommended=True)],
        )
    ],
)


@dataclass(frozen=True)
class _Edit:
    size: int | None = None
    expression: str | None = None
    passed: bool | None = None
    checked: bool = True
    gate: Gate | None = None
    reply: str | None = None
    read: bool = True


def _part(dest: Path, edit: _Edit) -> Path:
    shutil.copytree(_RUN / "turn-1", dest)
    captured = json.loads((dest / "wdk" / _STRATEGY).read_text())
    step = captured["response_json"]["steps"][_STEP]
    if edit.size is not None:
        step["estimatedSize"] = edit.size
    if edit.expression is not None:
        step["searchConfig"]["parameters"]["phyletic_expression"] = edit.expression
    captured["response_json"]["lastViewed"] = dest.name
    (dest / "wdk" / _STRATEGY).write_text(json.dumps(captured))
    if not edit.read:
        shutil.rmtree(dest / "wdk")
    snapshot = dest / "state" / "verification.json"
    if not edit.checked:
        snapshot.unlink()
    elif edit.passed is not None:
        held = json.loads(snapshot.read_text())
        held["ledger"]["verification"]["digest"]["success"] = edit.passed
        snapshot.write_text(json.dumps(held))
    if edit.gate is not None:
        (dest / "gate.json").write_text(edit.gate.model_dump_json(by_alias=True))
    if edit.reply is not None:
        (dest / "transcript.md").write_text(
            f"# Turn\n\n## Reply\n\n{edit.reply}\n\n## Assumed\n\n"
        )
    return dest


def test_the_last_turn_by_number_holds_the_observed_strategy_gate_and_check(
    tmp_path: Path,
) -> None:
    _part(tmp_path / "turn-2", _Edit(size=9, passed=True, gate=_QUESTION))
    _part(tmp_path / "turn-10", _Edit())

    observed = observed_from_run_directory(tmp_path)

    assert (
        observed.root_count,
        observed.ends_on,
        observed.verified,
        len(observed.turn_replies),
    ) == (1736, "none", False, 2)


def test_a_check_stands_while_the_strategy_is_the_one_it_read(
    tmp_path: Path,
) -> None:
    _part(tmp_path / "turn-1", _Edit(passed=True))
    _part(tmp_path / "turn-2", _Edit(checked=False))

    assert observed_from_run_directory(tmp_path).verified is True


def test_a_check_on_an_earlier_strategy_is_no_verdict(tmp_path: Path) -> None:
    _part(tmp_path / "turn-1", _Edit(passed=True))
    _part(tmp_path / "turn-2", _Edit(checked=False, expression="cand=1 AND cbov=1"))

    observed = observed_from_run_directory(tmp_path)

    assert (observed.verified, observed.tree is not None) == (None, True)


def test_a_card_answer_is_read_after_its_turn(tmp_path: Path) -> None:
    turn = _part(
        tmp_path / "turn-1",
        _Edit(
            gate=_QUESTION,
            reply="Which reading?",
            read=False,
            checked=False,
        ),
    )
    _part(turn / "answer-1", _Edit())

    observed = observed_from_run_directory(tmp_path)

    assert (
        observed.built_strategy,
        observed.root_count,
        observed.ends_on,
        len(observed.turn_replies),
    ) == (True, 1736, "none", 1)
    assert "1,736" in observed.reply_text


def test_a_question_the_run_ended_on_is_observed_with_its_options(
    tmp_path: Path,
) -> None:
    _part(tmp_path / "turn-1", _Edit(gate=_QUESTION))

    observed = observed_from_run_directory(tmp_path)

    assert (observed.ends_on, observed.consult_options) == (
        "consult",
        ["Every genome"],
    )


def test_a_case_stating_what_no_run_directory_holds_is_refused() -> None:
    case = load_case("orthomcl-one-protein-in-each-cryptosporidium-genome")
    stated = case.model_copy(
        update={
            "expected": case.expected.model_copy(
                update={"reply_gives_its_reasons": True, "passed_checks": 1}
            )
        }
    )

    with pytest.raises(UnobservedFieldError, match="replyGivesItsReasons"):
        score_run_directory(stated, _RUN, _crypto_tree(), "8.2")
    assert score_run_directory(case, _RUN, _crypto_tree(), "8.2").differences[
        0
    ].field == ("verified")


def test_a_run_that_read_no_strategy_built_nothing(tmp_path: Path) -> None:
    _part(tmp_path / "turn-1", _Edit(reply="Nothing ran.", read=False, checked=False))

    observed = observed_from_run_directory(tmp_path)

    assert (observed.built_strategy, observed.structure, observed.reply_text) == (
        False,
        None,
        "Nothing ran.",
    )


def test_the_facts_are_the_last_a_turn_showed(tmp_path: Path) -> None:
    turn = _part(tmp_path / "turn-1", _Edit())
    answer = _part(turn / "answer-1", _Edit())
    transcript = answer / "transcript.md"
    transcript.write_text(
        transcript.read_text().replace("Pattern: 1,736 groups", "Pattern: 1,737 groups")
    )
    _part(turn / "answer-2", _Edit(reply="Kept as built."))

    observed = observed_from_run_directory(tmp_path)

    assert observed.reply_text == "Kept as built."
    assert "Phyletic Pattern: 1,737 groups" in observed.facts_text


def _counted(case: EvalCase, count: int) -> EvalCase:
    recorded = case.expected.root_count
    assert recorded is not None
    return case.model_copy(
        update={
            "expected": case.expected.model_copy(
                update={"root_count": recorded.model_copy(update={"count": count})}
            )
        }
    )


def test_a_root_count_off_on_the_recorded_build_fails_the_run(tmp_path: Path) -> None:
    case = load_case("orthomcl-one-protein-in-each-cryptosporidium-genome")
    _part(tmp_path / "turn-1", _Edit(size=0, passed=True))

    counted = score_run_directory(_counted(case, 1), tmp_path, _crypto_tree(), "8.2")
    measured = score_run_directory(case, _RUN, _crypto_tree(), "8.2")

    assert (counted.verdict, counted.differences, counted.count_drift) == (
        "fail",
        [],
        CaseDifference(
            field="rootCount", expected="1 (build 8.2)", actual="0 (build 8.2)"
        ),
    )
    assert (measured.verdict, [d.field for d in measured.differences]) == (
        "fail",
        ["verified"],
    )


def test_a_root_count_on_a_newer_build_drifts_as_the_database_path_judges(
    tmp_path: Path,
) -> None:
    case = load_case("orthomcl-one-protein-in-each-cryptosporidium-genome")
    for size in (1800, 2000):
        _part(tmp_path / str(size) / "turn-1", _Edit(size=size, passed=True))

    verdicts = [
        score_run_directory(case, tmp_path / str(size), _crypto_tree(), build)
        for size, build in ((1800, "8.3"), (2000, "8.3"), (1800, "8.2"))
    ]

    assert [(v.verdict, v.observed_count) for v in verdicts] == [
        ("pass", 1800),
        ("re-measure", 2000),
        ("fail", 1800),
    ]


def _intersected(dest: Path) -> None:
    captured = json.loads((dest / "wdk" / _STRATEGY).read_text())
    held = captured["response_json"]
    leaf = held["steps"][_STEP]
    other = {
        **leaf,
        "id": 227284111,
        "searchConfig": {
            **leaf["searchConfig"],
            "parameters": {"phyletic_expression": "cand=1T"},
        },
    }
    combine = {
        **leaf,
        "id": 227284112,
        "searchName": "boolean_question_GroupRecordClasses_GroupRecordClass",
        "searchConfig": {
            **leaf["searchConfig"],
            "parameters": {"bq_operator": "INTERSECT"},
        },
    }
    held["steps"] = {_STEP: leaf, "227284111": other, "227284112": combine}
    held["rootStepId"] = 227284112
    held["stepTree"] = {
        "stepId": 227284112,
        "primaryInput": {"stepId": int(_STEP)},
        "secondaryInput": {"stepId": 227284111},
    }
    (dest / "wdk" / _STRATEGY).write_text(json.dumps(captured))


def test_the_observed_tree_holds_each_leafs_wire_values(tmp_path: Path) -> None:
    _intersected(_part(tmp_path / "turn-1", _Edit(expression="cbov=1T")))

    tree = observed_from_run_directory(tmp_path).tree

    assert tree == ComparisonNode(
        search_name=COMBINE_LABEL,
        operator="INTERSECT",
        parameters={},
        children=(
            ComparisonNode(
                search_name="GroupsByPhyleticPattern",
                parameters={"phyletic_expression": "cbov=1T"},
            ),
            ComparisonNode(
                search_name="GroupsByPhyleticPattern",
                parameters={"phyletic_expression": "cand=1T"},
            ),
        ),
    )
