from __future__ import annotations

import ast
import re
from pathlib import Path

from pathfinder.platform.identity import (
    FORMER_INTERNAL_STRATEGY_NAME_PREFIXES,
    VEUPATHDB_USER_AGENT,
)
from pathfinder.platform.principal import SERVICE_AUTH_HEADER

_APP = Path(__file__).resolve().parents[2]

_RETIRED = re.compile(r"\bPath[Ff]inder\b")

_WIRE_NAMES = frozenset({VEUPATHDB_USER_AGENT, *FORMER_INTERNAL_STRATEGY_NAME_PREFIXES})


def _application_files(pattern: str) -> list[Path]:
    return [
        path
        for path in sorted(_APP.rglob(pattern))
        if "tests" not in path.relative_to(_APP).parts
    ]


def _retired_strings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf8"))
    return [
        f"{path.relative_to(_APP)}:{node.lineno} {node.value!r}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _RETIRED.search(node.value)
        and not any(node.value in name for name in _WIRE_NAMES)
    ]


def test_no_application_string_names_the_retired_product() -> None:
    found = [
        hit for path in _application_files("*.py") for hit in _retired_strings(path)
    ]
    assert found == []


def test_no_prompt_names_the_retired_product() -> None:
    found = [
        str(path.relative_to(_APP))
        for path in _application_files("*.md")
        if _RETIRED.search(path.read_text(encoding="utf8"))
    ]
    assert found == []


def test_a_service_client_names_itself_under_the_new_product() -> None:
    assert SERVICE_AUTH_HEADER == "X-Strategist-Service-Token"


def test_the_sites_still_see_the_user_agent_their_operators_know() -> None:
    assert VEUPATHDB_USER_AGENT.startswith("PathFinder/")
