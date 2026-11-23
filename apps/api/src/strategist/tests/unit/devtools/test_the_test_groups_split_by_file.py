from __future__ import annotations

from pathlib import Path

import pytest

from strategist.devtools.split_tests import (
    file_seconds,
    main,
    partition_errors,
    split,
    tier_files,
)

DURATIONS = {
    "t/test_a.py::one": 6.0,
    "t/test_a.py::two[x]": 4.0,
    "t/test_b.py::one": 7.0,
    "t/test_c.py::one": 2.0,
    "t/test_d.py::one": 1.0,
}


def test_the_recorded_seconds_of_a_file_are_summed_over_its_tests() -> None:
    assert file_seconds(DURATIONS) == {
        "t/test_a.py": 10.0,
        "t/test_b.py": 7.0,
        "t/test_c.py": 2.0,
        "t/test_d.py": 1.0,
    }


def test_the_longest_file_goes_to_the_lightest_group_first() -> None:
    files = ["t/test_a.py", "t/test_b.py", "t/test_c.py", "t/test_d.py"]

    assert split(files, DURATIONS, 2) == [
        ["t/test_a.py"],
        ["t/test_b.py", "t/test_c.py", "t/test_d.py"],
    ]


def test_a_file_with_no_record_weighs_the_mean_of_the_recorded_files() -> None:
    files = ["t/test_a.py", "t/test_b.py", "t/test_new.py"]

    assert split(files, DURATIONS, 2) == [
        ["t/test_a.py"],
        ["t/test_b.py", "t/test_new.py"],
    ]


def test_a_partition_names_every_file_missing_doubled_or_unknown() -> None:
    files = ["t/test_a.py", "t/test_b.py", "t/test_c.py"]

    assert partition_errors(
        files, [["t/test_a.py", "t/test_x.py"], ["t/test_a.py"], []]
    ) == [
        "t/test_a.py is in 2 groups",
        "t/test_b.py is in no group",
        "t/test_c.py is in no group",
        "t/test_x.py is not a test file",
        "group 3 is empty",
    ]


def test_a_tier_lists_the_files_pytest_collects(tmp_path: Path) -> None:
    for name in (
        "test_a.py",
        "deep/test_b.py",
        "deep/c_test.py",
        "deep/helper.py",
        "conftest.py",
    ):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("")

    assert [
        Path(name).relative_to(tmp_path).as_posix() for name in tier_files(tmp_path)
    ] == [
        "deep/c_test.py",
        "deep/test_b.py",
        "test_a.py",
    ]


def test_the_committed_durations_split_both_tiers_into_whole_groups(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(Path(__file__).parents[5])

    assert main(["check", "unit:3", "integration:8"]) == 0
    assert capsys.readouterr().err == ""
