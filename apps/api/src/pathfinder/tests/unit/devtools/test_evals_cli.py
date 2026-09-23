"""The curation command's argument surface and its database-free subcommand."""

from __future__ import annotations

import pytest

from pathfinder.devtools.evals import _build_parser, main
from pathfinder.evals.case import ExpectedOutcome


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
        ],
    )

    assert not ExpectedOutcome.model_validate_json(args.expect).builds_strategy


def test_run_takes_a_case_filter_and_an_output_file() -> None:
    args = _build_parser().parse_args(["run", "--only", "a", "b", "--out", "s.json"])

    assert args.only == ["a", "b"]
    assert args.out == "s.json"


def test_run_uses_the_deterministic_provider_unless_asked_otherwise() -> None:
    parser = _build_parser()

    assert parser.parse_args(["run"]).real is False
    assert parser.parse_args(["run", "--real"]).real is True


def test_a_command_is_required() -> None:
    with pytest.raises(SystemExit):
        _build_parser().parse_args([])
