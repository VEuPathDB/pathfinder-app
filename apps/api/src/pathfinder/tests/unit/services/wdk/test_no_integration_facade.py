"""What the AI and transport layers may take from the WDK integration.

The layering contract names four ignored edges, and import-linter cannot see
which name each one imports. This does: the exception is one wire model, and it
shrinks to nothing when that model moves to the domain layer.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[4]
_CALLERS = ("ai", "transport")
_INTEGRATION = "pathfinder.integrations"
_ALLOWED_MODULE = "pathfinder.integrations.veupathdb.wdk_models"
_ALLOWED_NAMES = frozenset({"WDKSearch"})
_FACADE = _SOURCE_ROOT / "services" / "wdk" / "__init__.py"


@dataclass(frozen=True)
class _Import:
    module: str
    line: int
    name: str


def _integration_imports(source: str) -> list[_Import]:
    found: list[_Import] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if node.module != _INTEGRATION and not node.module.startswith(
            f"{_INTEGRATION}.",
        ):
            continue
        found.extend(
            _Import(node.module, node.lineno, alias.name) for alias in node.names
        )
    return found


def _caller_modules() -> list[tuple[str, str]]:
    return [
        (path.relative_to(_SOURCE_ROOT).as_posix(), path.read_text())
        for caller in _CALLERS
        for path in (_SOURCE_ROOT / caller).rglob("*.py")
    ]


def test_only_the_wire_search_model_crosses_from_the_integration() -> None:
    offenders = [
        (module, imported)
        for module, source in _caller_modules()
        for imported in _integration_imports(source)
        if imported.module != _ALLOWED_MODULE or imported.name not in _ALLOWED_NAMES
    ]

    assert offenders == []


def test_the_check_reports_a_client_import() -> None:
    source = "from pathfinder.integrations.veupathdb.client import VEuPathDBClient\n"

    assert _integration_imports(source) == [
        _Import("pathfinder.integrations.veupathdb.client", 1, "VEuPathDBClient"),
    ]


def test_the_wdk_service_package_exports_nothing() -> None:
    # A package that re-exports the integration inverts the contract into
    # architecture, so this one holds no code at all.
    assert _FACADE.read_text() == ""
