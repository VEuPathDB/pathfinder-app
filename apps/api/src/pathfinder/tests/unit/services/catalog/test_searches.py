"""The search-catalog half: the query guard, and the surface it keeps clean.

Every function here takes a site and its arguments by value. It holds no agent
state and imports nothing from ``pathfinder.ai``, so the MCP server can call the
same code the in-process tools call.
"""

from __future__ import annotations

import ast
from importlib.util import resolve_name
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

import pathfinder
from pathfinder.services.catalog import searches
from pathfinder.services.catalog.search_inspection import (
    inspect_search,
    read_parameter_options,
)
from pathfinder.services.catalog.searches import VagueSearchQueryError


class TestSearchQueryGuard:
    async def test_an_empty_query_is_refused(self) -> None:
        with pytest.raises(VagueSearchQueryError) as excinfo:
            await searches.search_for_searches("plasmodb", "transcript", "")

        assert excinfo.value.rejection.error == "query_required"

    async def test_a_one_word_query_is_refused(self) -> None:
        with pytest.raises(VagueSearchQueryError) as excinfo:
            await searches.search_for_searches("plasmodb", "transcript", "gene")

        rejection = excinfo.value.rejection
        assert rejection.error == "query_too_vague"
        assert rejection.query == "gene"
        assert rejection.examples

    async def test_keywords_carry_a_short_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded: dict[str, Any] = {}

        async def _resolve(*_a: Any, **_k: Any) -> list[str]:
            recorded["called"] = True
            return ["transcript"]

        monkeypatch.setattr(searches, "resolve_record_types", _resolve)
        monkeypatch.setattr(searches, "get_discovery_service", MagicMock())

        async def _collect(*_a: Any, **_k: Any) -> list[Any]:
            return []

        async def _no_bonus(*_a: Any, **_k: Any) -> None:
            return None

        monkeypatch.setattr(searches, "collect_search_candidates", _collect)
        monkeypatch.setattr(searches, "apply_site_search_bonus", _no_bonus)
        monkeypatch.setattr(searches, "apply_semantic_bonus", _no_bonus)

        result = await searches.search_for_searches(
            "plasmodb", "transcript", "gene", keywords=["Su_strand_specific"]
        )

        assert result == []
        assert recorded["called"] is True


_SOURCE_ROOT = Path(pathfinder.__file__).parent.parent
_SERVICE_ENTRY_POINTS = (
    "pathfinder.services.catalog.search_inspection",
    "pathfinder.services.catalog.searches",
)


def _source_of(module: str) -> Path | None:
    """The file a first-party module lives in. ``None`` for a third-party name."""
    base = _SOURCE_ROOT.joinpath(*module.split("."))
    single = base.with_suffix(".py")
    if single.is_file():
        return single
    package = base / "__init__.py"
    return package if package.is_file() else None


def _imports_of(module: str, path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            package = module.rsplit(".", 1)[0] if path.name != "__init__.py" else module
            names.add(
                resolve_name("." * node.level + (node.module or ""), package)
                if node.level
                else (node.module or "")
            )
    return names


def _modules_reachable_from(entry_points: tuple[str, ...]) -> set[str]:
    """Every module name the entry points pull in, first-party walk, leaves included."""
    seen: set[str] = set()
    pending = list(entry_points)
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        source = _source_of(module)
        if source is not None:
            pending.extend(_imports_of(module, source))
    return seen


class TestTheServiceHalfCarriesNoAgentSurface:
    def test_nothing_it_reaches_imports_pydantic_ai(self) -> None:
        """The MCP server holds no agent framework, so the read must load without one."""
        reached = _modules_reachable_from(_SERVICE_ENTRY_POINTS)

        assert [
            name for name in sorted(reached) if name.startswith("pydantic_ai")
        ] == []

    def test_the_control_module_is_caught(self) -> None:
        """The walk finds a real dependency, so a green result is not a blind spot."""
        reached = _modules_reachable_from(
            ("pathfinder.ai.tools.standalone.catalog_discovery",)
        )

        assert "pydantic_ai" in reached

    def test_the_split_halves_take_a_site_and_no_state(self) -> None:
        signatures = {
            "inspect_search": inspect_search,
            "read_parameter_options": read_parameter_options,
            "search_for_searches": searches.search_for_searches,
            "list_searches": searches.list_searches,
        }

        for name, function in signatures.items():
            params = list(
                function.__code__.co_varnames[: function.__code__.co_argcount]
            )
            assert params[0] == "site_id", name
            assert "ctx" not in params, name
            assert "agent_state" not in params, name
            assert "deps" not in params, name
