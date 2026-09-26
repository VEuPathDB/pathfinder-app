"""The corpus on disk: one file per case, listed and loaded by name."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from pathfinder.evals.case import (
    CaseProvenance,
    EvalCase,
    ExpectedOutcome,
    GateAnswer,
)
from pathfinder.evals.redaction import RedactionFailedError
from pathfinder.evals.store import (
    CORPUS_DIR,
    case_names,
    load_case,
    load_corpus,
    write_case,
)


def _case(name: str) -> EvalCase:
    return EvalCase(
        name=name,
        turns=["find kinases"],
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins the build path",
        expected=ExpectedOutcome(builds_strategy=True),
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="promoted",
            staging_id="0f0f",
            added_at="2026-08-23",
        ),
    )


def test_the_shipped_corpus_loads(tmp_path: Path) -> None:
    del tmp_path

    corpus = load_corpus()

    assert corpus, f"no case files under {CORPUS_DIR}"


def test_every_shipped_case_is_de_identified() -> None:
    for case in load_corpus():
        assert case.assert_de_identified()


def test_every_shipped_case_names_its_file() -> None:
    for case in load_corpus():
        assert (CORPUS_DIR / f"{case.name}.json").is_file()


def test_a_written_case_reads_back_unchanged(tmp_path: Path) -> None:
    written = write_case(_case("a-new-case"), directory=tmp_path)

    assert written.is_file()
    assert load_case("a-new-case", directory=tmp_path) == _case("a-new-case")


def test_writing_over_an_existing_case_is_refused(tmp_path: Path) -> None:
    write_case(_case("a-new-case"), directory=tmp_path)

    with pytest.raises(FileExistsError, match="a-new-case"):
        write_case(_case("a-new-case"), directory=tmp_path)


def test_a_missing_case_names_the_promote_command(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="promote"):
        load_case("not-here", directory=tmp_path)


def test_names_are_sorted(tmp_path: Path) -> None:
    write_case(_case("b-case"), directory=tmp_path)
    write_case(_case("a-case"), directory=tmp_path)

    assert case_names(directory=tmp_path) == ["a-case", "b-case"]


def test_a_case_names_at_least_one_turn() -> None:
    with pytest.raises(ValidationError, match="turns"):
        EvalCase(
            name="a-case",
            turns=[],
            site_id="plasmodb",
            assistant_id="pathfinder",
            rationale="pins the build path",
            expected=ExpectedOutcome(builds_strategy=True),
            provenance=CaseProvenance(
                site="plasmodb",
                assistant="pathfinder",
                origin="promoted",
                staging_id="0f0f",
                added_at="2026-08-23",
            ),
        )


def test_every_shipped_case_states_its_turns() -> None:
    for case in load_corpus():
        assert case.turns
        assert all(turn.strip() for turn in case.turns)


_EMAIL = "someone@example.org"


@pytest.mark.parametrize(
    "update",
    [
        {"turns": [f"write to {_EMAIL}"]},
        {"rationale": f"asked by {_EMAIL}"},
        {"expected": ExpectedOutcome(builds_strategy=True, reply_mentions=[_EMAIL])},
        {"expected": ExpectedOutcome(builds_strategy=True, reply_omits=[_EMAIL])},
        {"expected": ExpectedOutcome(builds_strategy=True, step_titles_omit=[_EMAIL])},
        {
            "expected": ExpectedOutcome(
                builds_strategy=True,
                parameters={"GenesByText": {"text_expression": _EMAIL}},
            )
        },
        {"attachments": {0: [f"{_EMAIL}.csv"]}},
        {"gates": [GateAnswer(accept=False, comment=f"ask {_EMAIL}")]},
        {"gates": [GateAnswer(picks=[_EMAIL])]},
        {
            "provenance": CaseProvenance(
                site="plasmodb",
                assistant="pathfinder",
                origin="promoted",
                staging_id="0f0f",
                added_at="2026-08-23",
                curator_note=f"from {_EMAIL}",
            )
        },
    ],
    ids=[
        "turn",
        "rationale",
        "reply-mentions",
        "reply-omits",
        "step-titles-omit",
        "parameter-value",
        "attachment-name",
        "gate-comment",
        "question-pick",
        "curator-note",
    ],
)
def test_every_free_text_field_is_checked_for_an_identity(
    update: dict[str, object],
) -> None:
    case = _case("a-case").model_copy(update=update)

    with pytest.raises(RedactionFailedError, match="email"):
        case.assert_de_identified()
