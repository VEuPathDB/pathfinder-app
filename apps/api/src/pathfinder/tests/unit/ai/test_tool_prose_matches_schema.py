"""The prose a tool shows the model names only what the tool declares."""

from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent
from pydantic_ai.tools import Tool
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset

from pathfinder.ai.agents.execution import build_execution_agent
from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.verification import build_verification_agent
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.lead_agent import build_lead_agent


class _Property(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: str = ""


class _ToolSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    properties: dict[str, _Property] = Field(default_factory=dict)


def _function_tools(agent: Agent[Any, Any]) -> dict[str, Tool[Any]]:
    found: dict[str, Tool[Any]] = {}
    for toolset in agent.toolsets:
        inner: Any = toolset
        while isinstance(inner, WrapperToolset):
            inner = inner.wrapped
        if isinstance(inner, FunctionToolset):
            found.update(inner.tools)
    return found


def _inventory() -> dict[str, Tool[Any]]:
    found: dict[str, Tool[Any]] = {}
    for build in (
        build_lead_agent,
        build_frame_agent,
        build_execution_agent,
        build_verification_agent,
    ):
        found.update(_function_tools(build()))
    return found


_TOOLS = _inventory()
_TOOL_NAMES = frozenset(_TOOLS)
_TOOL_VERBS = frozenset(name.split("_")[0] for name in _TOOL_NAMES)

_QUOTED = re.compile(r"``([^`\n]+)``|`([^`\n]+)`")
_SNAKE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")


def _schema_of(tool: Tool[Any]) -> _ToolSchema:
    return _ToolSchema.model_validate(tool.function_schema.json_schema)


_DECLARED_ANYWHERE = frozenset(
    name for tool in _TOOLS.values() for name in _schema_of(tool).properties
)


def _camel_of(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(word.capitalize() for word in rest)


def _prose_of(tool: Tool[Any]) -> str:
    schema = _schema_of(tool)
    parts = [tool.description or ""]
    parts.extend(prop.description for prop in schema.properties.values())
    return "\n".join(parts)


def _raises_model_retry(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ModelRetry"
    )


def _not_prose(tree: ast.AST) -> set[int]:
    """Dict keys and docstrings, by node identity.

    A dict key is a wire field and a docstring already reaches the model
    through the tool schema, so neither one is retry prose.
    """
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            found.update(id(key) for key in node.keys if isinstance(key, ast.Constant))
        if not isinstance(
            node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        ):
            continue
        first = node.body[0] if node.body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            found.add(id(first.value))
    return found


def _retry_prose(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    skip = _not_prose(tree)
    texts: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not any(_raises_model_retry(child) for child in ast.walk(node)):
            continue
        texts.extend(
            child.value
            for child in ast.walk(node)
            if isinstance(child, ast.Constant)
            and isinstance(child.value, str)
            and id(child) not in skip
        )
    return "\n".join(texts)


def _source_path(tool: Tool[Any]) -> Path | None:
    found = inspect.getsourcefile(inspect.unwrap(tool.function))
    return Path(found) if found else None


def _model_facing_text(tool: Tool[Any]) -> str:
    path = _source_path(tool)
    retries = _retry_prose(path) if path else ""
    return f"{_prose_of(tool)}\n{retries}"


def _camel_offenders(declared: list[str], text: str) -> list[str]:
    return sorted(
        {
            _camel_of(name)
            for name in declared
            if "_" in name and re.search(rf"\b{_camel_of(name)}\b", text)
        }
    )


def _quoted_snake_tokens(text: str) -> set[str]:
    found: set[str] = set()
    for match in _QUOTED.finditer(text):
        token = (match.group(1) or match.group(2)).strip().removesuffix("()").strip()
        if _SNAKE.match(token):
            found.add(token)
    return found


@pytest.mark.parametrize("tool_name", sorted(_TOOL_NAMES))
def test_no_prose_or_retry_names_a_parameter_in_camel_case(tool_name: str) -> None:
    """A camelCase argument name in prose earns an extra_forbidden retry."""
    tool = _TOOLS[tool_name]
    declared = list(_schema_of(tool).properties)
    offenders = _camel_offenders(declared, _model_facing_text(tool))
    assert offenders == [], f"{tool_name} prose names {offenders}"


@pytest.mark.parametrize("tool_name", sorted(_TOOL_NAMES))
def test_every_quoted_tool_name_resolves_to_a_registered_tool(tool_name: str) -> None:
    """A tool name in prose that nobody registers sends the model nowhere."""
    tool = _TOOLS[tool_name]
    quoted = _quoted_snake_tokens(_prose_of(tool))
    tool_shaped = {
        token
        for token in quoted
        if token.split("_")[0] in _TOOL_VERBS and token not in _DECLARED_ANYWHERE
    }
    unknown = sorted(tool_shaped - _TOOL_NAMES)
    assert unknown == [], f"{tool_name} prose names unregistered tools: {unknown}"


def test_the_lead_instructions_name_no_parameter_in_camel_case() -> None:
    """The Lead reads the same argument names its tools declare."""
    offenders = _camel_offenders(sorted(_DECLARED_ANYWHERE), LEAD_INSTRUCTIONS)
    assert offenders == [], f"LEAD_INSTRUCTIONS names {offenders}"


def test_the_inventory_reaches_every_phase() -> None:
    """A short inventory would pass every check above without testing it."""
    assert len(_TOOL_NAMES) >= 75
    for name in ("verify_strategy", "set_criterion", "build_strategy"):
        assert name in _TOOL_NAMES, name
    for name in ("run_eda_compute", "run_control_tests_on_step", "list_notes"):
        assert name in _TOOL_NAMES, name
