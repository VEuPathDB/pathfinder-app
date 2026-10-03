"""The curation command's argument surface and its database-free subcommand."""

from __future__ import annotations

import pytest

from pathfinder.devtools import evals
from pathfinder.devtools.evals import _build_parser, main
from pathfinder.evals.case import ExpectedOutcome, GatePlan
from pathfinder.evals.summary import CaseResult, EvalRunSummary


def test_corpus_lists_the_shipped_cases(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["corpus"]) == 0

    printed = capsys.readouterr().out
    assert "case(s) in" in printed
    assert "remember-request-does-not-build" in printed


def test_a_case_that_accepts_either_outcome_is_listed_as_either(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["corpus"]) == 0

    row = next(
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("a-search-the-site-lacks-is-named-or-asked")
    )
    assert row.split()[1:3] == ["plasmodb", "either"]


def test_promote_requires_a_name_and_a_rationale() -> None:
    parser = _build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["promote", "some-id"])


def test_promote_accepts_an_expectation_as_json() -> None:
    args = _build_parser().parse_args(
        [
            "promote",
            "some-id",
            "--name",
            "a-case",
            "--rationale",
            "pins a thing",
            "--expect",
            '{"buildsStrategy": false}',
            "--gates",
            '{"policy": "decline-offers"}',
        ],
    )

    assert not ExpectedOutcome.model_validate_json(args.expect).builds_strategy
    assert GatePlan.model_validate_json(args.gates).policy == "decline-offers"


def test_promote_requires_the_case_to_state_its_gate_policy() -> None:
    parser = _build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["promote", "some-id", "--name", "a", "--rationale", "r"])


def test_run_takes_a_case_filter_and_an_output_file() -> None:
    args = _build_parser().parse_args(["run", "--only", "a", "b", "--out", "s.json"])

    assert args.only == ["a", "b"]
    assert args.out == "s.json"


def test_run_has_no_provider_switch() -> None:
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["run", "--real"])


def test_run_can_hand_every_turn_to_the_worker() -> None:
    parser = _build_parser()

    assert parser.parse_args(["run"]).via_worker is False
    assert parser.parse_args(["run", "--via-worker"]).via_worker is True


def test_run_takes_one_effort_for_every_role() -> None:
    parser = _build_parser()

    assert parser.parse_args(["run"]).effort is None
    assert parser.parse_args(["run", "--effort", "high"]).effort == "high"
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--effort", "max"])


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit):
        _build_parser().parse_args([])


def test_a_case_not_run_is_printed_as_not_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def _run_corpus(**options: object) -> EvalRunSummary:
        del options
        return EvalRunSummary(
            harness="pydantic-evals",
            provider="mock",
            assistant_id="pathfinder",
            ran_at="2026-08-23T00:00:00+00:00",
            cases=[
                CaseResult(
                    name="uat-s1-cryptodb",
                    verdict="not-run",
                    error="cryptodb login did not answer (connect timeout)",
                ),
                CaseResult(name="uat-s1-plasmodb", verdict="pass"),
            ],
        )

    monkeypatch.setattr(evals, "run_corpus", _run_corpus)

    assert main(["run"]) == 0

    printed = capsys.readouterr().out.splitlines()
    assert printed[0].startswith("NOT RUN  uat-s1-cryptodb")
    assert printed[1] == "      cryptodb login did not answer (connect timeout)"
    assert printed[-1].startswith(
        "--- 1/2 passed (re-measure 0, failed 0, errored 0, not run 1)"
    )
