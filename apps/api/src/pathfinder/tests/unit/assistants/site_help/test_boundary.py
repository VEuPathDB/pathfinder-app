"""The pilot is proof that a simple assistant needs none of PathFinder.

The runtime it builds on is an installed package. What it reaches inside this
application is pinned below; a single import of ``pathfinder.ai`` would mean
the claim is untested.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from pathlib import Path
from types import ModuleType

import pytest

from pathfinder.assistants import site_help

PILOT = site_help.__name__

REACHED = {
    "pathfinder.platform.config",
    "pathfinder.platform.tool_sources",
    "veupathdb_mcp.catalog",
}


def _pilot_modules() -> list[ModuleType]:
    return [
        site_help,
        *(
            importlib.import_module(info.name)
            for info in pkgutil.walk_packages(site_help.__path__, prefix=f"{PILOT}.")
        ),
    ]


def _host_imports(module: ModuleType) -> set[str]:
    path = module.__file__
    assert path is not None
    names: set[str] = set()
    for node in ast.walk(ast.parse(Path(path).read_text())):
        if isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return {
        name
        for name in names
        if name.startswith(("pathfinder", "veupathdb_mcp"))
        and not name.startswith(f"{PILOT}.")
    }


@pytest.mark.parametrize("module", _pilot_modules(), ids=lambda m: m.__name__)
def test_no_pilot_module_imports_pathfinder_s_orchestration(
    module: ModuleType,
) -> None:
    assert not any(name.startswith("pathfinder.ai") for name in _host_imports(module))


def test_the_surface_the_pilot_reaches_has_not_grown() -> None:
    reached = {name for m in _pilot_modules() for name in _host_imports(m)}

    assert reached == REACHED
