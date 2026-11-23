from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).parents[4] / "scripts" / "check_weak_assertions.py"
_FILE = Path("test_sample.py")


def _check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_weak_assertions", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _flagged(body: str) -> list[tuple[int, str]]:
    source = f"def test_it(items: list[int]) -> None:\n{body}"
    weak, nonempty = _check().scan_source(source, _FILE)
    return [(line, reason) for _, line, _, reason in [*weak, *nonempty]]


@pytest.mark.parametrize(
    "check",
    [
        "len(items) > 0",
        "len(items) >= 1",
        "len(items) != 0",
        "0 < len(items)",
        "1 <= len(items)",
        "0 != len(items)",
        "items != []",
        "() != items",
        "items != {}",
    ],
)
def test_a_non_empty_check_is_flagged_on_its_line(check: str) -> None:
    body = f"    assert items == [1]\n    assert {check}\n"

    assert _flagged(body) == [(3, "nonempty_check")]


def test_a_non_empty_check_alone_also_makes_the_test_weak() -> None:
    assert _flagged("    assert len(items) > 0\n") == [
        (1, "only_weak_assertions"),
        (2, "nonempty_check"),
    ]


@pytest.mark.parametrize(
    "body",
    [
        "    assert len(items) > 0  # weak-ok(nonempty): the site decides the count\n",
        "    # weak-ok(nonempty): the site decides the count\n    assert len(items) > 0\n",
    ],
)
def test_a_justified_non_empty_check_counts_as_strong(body: str) -> None:
    assert _flagged(body) == []


def test_a_marker_without_a_reason_justifies_nothing() -> None:
    body = "    assert len(items) > 0  # weak-ok(nonempty):\n    assert items[0] == 1\n"

    assert _flagged(body) == [(2, "nonempty_check")]


@pytest.mark.parametrize(
    "check",
    ["len(items) == 2", "len(items) > 1", "len(items) >= 2", "items != [1]"],
)
def test_a_count_or_a_value_is_not_a_non_empty_check(check: str) -> None:
    assert _flagged(f"    assert {check}\n") == []
