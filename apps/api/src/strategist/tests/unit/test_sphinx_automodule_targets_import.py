"""Every ``automodule::`` target under ``docs`` names a module that imports.

Sphinx runs without ``-W``, so a target with no module behind it renders the
prose and nothing under it. This test is the gate instead.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

_DOCS = Path(__file__).resolve().parents[4] / "docs"
_AUTOMODULE = re.compile(r"^\.\.\s+automodule::\s+(\S+)\s*$", re.MULTILINE)


def _targets() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for rst in sorted(_DOCS.rglob("*.rst")):
        page = rst.relative_to(_DOCS).as_posix()
        found.extend(
            (page, match.group(1)) for match in _AUTOMODULE.finditer(rst.read_text())
        )
    return found


_TARGETS = _targets()


def test_the_docs_tree_still_carries_automodule_targets() -> None:
    assert len(_TARGETS) > 100, f"only {len(_TARGETS)} targets found under {_DOCS}"


@pytest.mark.parametrize(
    ("page", "module"), _TARGETS, ids=[f"{p}::{m}" for p, m in _TARGETS]
)
def test_every_automodule_target_imports(page: str, module: str) -> None:
    try:
        importlib.import_module(module)
    except ImportError as exc:
        pytest.fail(f"docs/{page} points autodoc at {module}, which fails: {exc}")
