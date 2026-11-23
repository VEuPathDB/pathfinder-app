"""Every unit-test directory names a package that exists."""

from __future__ import annotations

from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_PACKAGE = _TESTS.parents[1]
_SCRIPTED = _PACKAGE.parent / "strategist_scripted"
_IGNORED = {"__pycache__", ".hypothesis", ".pytest_cache"}


def _test_directories() -> list[Path]:
    return sorted(
        directory
        for directory in _TESTS.rglob("*")
        if directory.is_dir()
        and not (_IGNORED & set(directory.relative_to(_TESTS).parts))
    )


def _source_of(relative: Path) -> Path:
    if relative.parts[0] == "scripted":
        return _SCRIPTED.joinpath(*relative.parts[1:])
    return _PACKAGE / relative


def test_every_unit_test_directory_mirrors_a_source_package() -> None:
    """A directory under `tests/unit/` names a package under `src/strategist/`."""
    orphans = [
        directory.relative_to(_TESTS).as_posix()
        for directory in _test_directories()
        if not _source_of(directory.relative_to(_TESTS)).is_dir()
    ]
    assert orphans == []


def test_the_check_reads_a_real_tree() -> None:
    """The sweep is not vacuous: it walks directories that exist."""
    walked = {
        directory.relative_to(_TESTS).as_posix() for directory in _test_directories()
    }
    assert {
        "ai",
        "ai/tools",
        "domain",
        "platform",
        "services/eda",
        "scripted/models",
    } <= walked
