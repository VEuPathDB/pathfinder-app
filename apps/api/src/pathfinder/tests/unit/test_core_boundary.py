"""The runtime is a package, not a directory.

``assistant-core`` installs into this application; the application does not
install into it. The dependency edge points one way, so the science cannot
reach the runtime's modules even by mistake.
"""

from __future__ import annotations

from importlib.metadata import distribution
from pathlib import Path

import assistant_core

import pathfinder

CORE_DISTRIBUTION = "assistant-core"
SCIENCE_DISTRIBUTION = "pathfinder-api"


def _requires(name: str) -> list[str]:
    return [raw.lower() for raw in distribution(name).requires or []]


def test_the_runtime_ships_as_its_own_distribution() -> None:
    assert distribution(CORE_DISTRIBUTION).metadata["Name"] == CORE_DISTRIBUTION


def test_the_science_depends_on_the_runtime() -> None:
    assert any(
        raw.startswith(CORE_DISTRIBUTION) for raw in _requires(SCIENCE_DISTRIBUTION)
    )


def test_the_runtime_depends_on_no_part_of_the_science() -> None:
    assert not any(
        raw.startswith(SCIENCE_DISTRIBUTION) for raw in _requires(CORE_DISTRIBUTION)
    )


def test_the_runtime_source_lives_outside_the_science() -> None:
    core_root = Path(assistant_core.__file__ or "").resolve().parent
    science_root = Path(pathfinder.__file__ or "").resolve().parent

    assert science_root not in core_root.parents
    assert core_root != science_root
