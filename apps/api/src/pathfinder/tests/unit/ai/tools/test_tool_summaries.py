"""Every registered tool says, in one line, what its call did.

The enumeration is the point: a tool added without a summary fails here rather
than reaching a reader as a bare row.
"""

from __future__ import annotations

import ast
import inspect
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.tool_summary import truncate_summary
from pydantic_ai import Agent
from pydantic_ai.toolsets.abstract import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset
from pydantic_ai.ui.vercel_ai.response_types import BaseChunk

from pathfinder.ai.agents.execution import build_execution_agent
from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.verification import build_verification_agent
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.tools.standalone import (
    eda_compute,
    experiment,
    optimization,
    workbench,
)
from pathfinder.assistants.site_help.agent import build_site_help_agent
from pathfinder.tests.unit.ai.tools.conftest import summary_chunks

_SUMMARY_BUILDERS = frozenset({"with_summary", "summary_chunks"})

# A sub-agent dispatch's native tool chunks never reach the wire; its line
# rides the data-sub-agent-call payload, so a summary naming its call would
# patch nothing.
_SUB_AGENT_DISPATCH_MODULES = frozenset(
    {
        "pathfinder.ai.lead.frame_dispatch",
        "pathfinder.ai.lead.sub_agent_dispatch",
        "pathfinder.ai.lead.verify_dispatch",
        "pathfinder.ai.lead.edit_dispatch",
    }
)

# A tool that returns another tool's ToolReturn carries that tool's summary,
# which names the same call.
_DELEGATES = {"request_search_inspection": "get_search_overview"}

# The four durable tools never run their own body: the summary is built from
# the resumed payload instead, so it is driven rather than read.
_DURABLE_BUILDERS: dict[str, Callable[[Any, UUID, str | None], list[BaseChunk]]] = {
    "run_control_tests_on_step": experiment._control_test_chunks_from_result,
    "optimize_search_parameters": optimization._sweep_chunks_from_result,
    "run_eda_compute": eda_compute._compute_chunks_from_result,
    "run_gene_set_enrichment": workbench._enrichment_chunks_from_result,
}


def _functions(toolset: AbstractToolset[Any]) -> dict[str, Callable[..., Any]]:
    while isinstance(toolset, WrapperToolset):
        toolset = toolset.wrapped
    if not isinstance(toolset, FunctionToolset):
        return {}
    return {name: tool.function for name, tool in toolset.tools.items()}


def _agent_functions(agent: Agent[Any, Any]) -> dict[str, Callable[..., Any]]:
    found: dict[str, Callable[..., Any]] = {}
    for toolset in agent.toolsets:
        found |= _functions(toolset)
    return found


def _registered() -> dict[str, Callable[..., Any]]:
    """Every tool an agent of this application can call, by name."""
    found: dict[str, Callable[..., Any]] = {}
    for build in (
        build_frame_agent,
        build_execution_agent,
        build_verification_agent,
        build_lead_agent,
        build_site_help_agent,
    ):
        found |= _agent_functions(build())
    return found


def _every_implementation() -> list[tuple[str, Callable[..., Any]]]:
    """Each (name, function) pair, so one name on two functions checks both.

    ``build_strategy`` is the Lead's dispatch on one surface and the
    declarative build on another; a map keyed by name would hide one of them.
    """
    pairs: list[tuple[str, Callable[..., Any]]] = []
    seen: set[tuple[str, str]] = set()
    for build in (
        build_frame_agent,
        build_execution_agent,
        build_verification_agent,
        build_lead_agent,
        build_site_help_agent,
    ):
        for name, fn in _agent_functions(build()).items():
            key = (name, f"{fn.__module__}.{fn.__qualname__}")
            if key in seen:
                continue
            seen.add(key)
            pairs.append((name, fn))
    return pairs


def _module_tree(fn: Callable[..., Any]) -> ast.Module:
    source = Path(inspect.getsourcefile(fn) or "").read_text()
    return ast.parse(source)


def _defs_for(
    fn: Callable[..., Any],
) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """The definitions on the return path of one tool.

    A tool's own module answers first. A helper it imports from the same
    distribution is on that path too, so the module holding the helper
    contributes the names the tool's module does not define.
    """
    defs = _defs(_module_tree(fn))
    root = f"/{fn.__module__.split('.')[0]}/"
    parsed: dict[str, ast.Module] = {}
    for value in list(fn.__globals__.values()):
        if not inspect.isfunction(value):
            continue
        path = inspect.getsourcefile(value)
        if path is None or root not in path:
            continue
        if path not in parsed:
            parsed[path] = ast.parse(Path(path).read_text())
        for name, node in _defs(parsed[path]).items():
            defs.setdefault(name, node)
    return defs


def _called_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
    return names


def _defs(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function a module defines, including one built inside a factory."""
    return {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def _own_body(node: ast.AST) -> list[ast.AST]:
    """Every node of one function, skipping the functions nested inside it."""
    nested = {
        inner
        for child in ast.iter_child_nodes(node)
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        for inner in ast.walk(child)
    }
    return [
        child for child in ast.walk(node) if child is not node and child not in nested
    ]


def _assigned(node: ast.AST, name: str) -> list[ast.expr]:
    """Every expression bound to ``name`` inside one function."""
    return [
        child.value
        for child in _own_body(node)
        if isinstance(child, ast.Assign)
        and any(t.id == name for t in child.targets if isinstance(t, ast.Name))
    ]


def _is_a_summary(
    expr: ast.expr,
    node: ast.AST,
    defs: dict[str, Any],
    known: set[str],
    memo: dict[str, bool],
) -> bool:
    """The expression is, or resolves to, a value carrying a summary chunk."""
    if isinstance(expr, ast.Await):
        return _is_a_summary(expr.value, node, defs, known, memo)
    if isinstance(expr, ast.Name):
        return any(
            _is_a_summary(bound, node, defs, known, memo)
            for bound in _assigned(node, expr.id)
        )
    if not isinstance(expr, ast.Call):
        return False
    func = expr.func
    called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
    if called in _SUMMARY_BUILDERS or called in known:
        return True
    return _reaches_a_summary(called, defs, known, memo)


def _reaches_a_summary(
    name: str,
    defs: dict[str, Any],
    known: set[str],
    memo: dict[str, bool],
) -> bool:
    """Every value the function returns carries a summary chunk.

    Reaching a builder on one branch is not enough: a tool whose success path
    forgot its line would still reach one through its refusal.
    """
    if name in memo:
        return memo[name]
    if name not in defs:
        return False
    memo[name] = False
    node = defs[name]
    returned = [
        child.value
        for child in _own_body(node)
        if isinstance(child, ast.Return) and child.value is not None
    ]
    answer = bool(returned) and all(
        _is_a_summary(expr, node, defs, known, memo) for expr in returned
    )
    memo[name] = answer
    return answer


def _summary_literals(tree: ast.Module) -> list[str]:
    """The literal text of every summary a module writes."""
    lines: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.id if isinstance(func, ast.Name) else ""
        if called not in _SUMMARY_BUILDERS or len(node.args) < 2:
            continue
        lines.append(_literal_text(node.args[1]))
    return [line for line in lines if line]


def _literal_text(node: ast.expr) -> str:
    """The constant parts of a summary expression, with holes removed."""
    if isinstance(node, ast.Call) and node.args:
        return _literal_text(node.args[0])
    return "".join(
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    )


def test_every_registered_tool_emits_a_summary() -> None:
    registered = _registered()
    every = _every_implementation()
    assert len(registered) >= 80, "the enumeration lost a surface"
    assert len(every) > len(registered), "a name on two functions is checked twice"
    missing: list[str] = []
    for name, fn in every:
        if name in _DURABLE_BUILDERS or fn.__module__ in _SUB_AGENT_DISPATCH_MODULES:
            continue
        target = _DELEGATES.get(name, name)
        source = registered[target] if target != name else fn
        defs = _defs_for(source)
        if not _reaches_a_summary(target, defs, set(registered), {}):
            missing.append(f"{fn.__module__}.{name}")
    assert not missing, f"tools that write no summary: {sorted(missing)}"


def test_the_durable_tools_summarize_their_resumed_result() -> None:
    """A durable tool's body never runs, so its summary rides the resume."""
    registered = _registered()
    resumed: dict[str, dict[str, Any]] = {
        "run_control_tests_on_step": {
            "positiveIntersection": 8,
            "positiveControlsCount": 10,
        },
        "optimize_search_parameters": {
            "variants": [{}, {}],
            "best": {"score": 0.5},
            "objective": "mcc",
        },
        "run_eda_compute": {
            "genesTested": 5511,
            "retainedUp": 900,
            "retainedDown": 643,
        },
        "run_gene_set_enrichment": {
            "totalSignificantTerms": 12,
            "analysisTypesRun": ["go_process", "pathway"],
        },
    }
    for name, build in _DURABLE_BUILDERS.items():
        assert name in registered, f"{name} is not registered"
        chunks = build(
            {"status": "success", "result": resumed[name]}, uuid4(), "call_1"
        )
        summaries = summary_chunks(chunks)
        assert len(summaries) == 1, name
        assert summaries[0].data["toolCallId"] == "call_1"


def test_a_durable_summary_is_dropped_when_the_call_has_no_id() -> None:
    for name, build in _DURABLE_BUILDERS.items():
        chunks = build({"status": "success", "result": {}}, uuid4(), None)
        assert summary_chunks(chunks) == [], name


def test_no_summary_repeats_the_tool_name() -> None:
    registered = set(_registered())
    for module in _summary_modules():
        for line in _summary_literals(module):
            assert "successfully" not in line.lower(), line
            assert "{" not in line, line
            assert "}" not in line, line
            assert "\n" not in line, line
            words = set(re.findall(r"[a-z_][a-z0-9_]*", line))
            named = sorted(registered & words)
            assert not named, f"{line!r} names {named}"


def test_no_summary_exceeds_the_limit() -> None:
    """The fixed part of a summary leaves room for what it interpolates."""
    for module in _summary_modules():
        for line in _summary_literals(module):
            assert len(line) <= 120, line


def test_no_summary_ends_with_a_period() -> None:
    for module in _summary_modules():
        for line in _summary_literals(module):
            assert not line.endswith("."), line


def _summary_modules() -> list[ast.Module]:
    seen: set[str] = set()
    trees: list[ast.Module] = []
    for fn in _registered().values():
        path = inspect.getsourcefile(fn) or ""
        if path in seen:
            continue
        seen.add(path)
        trees.append(_module_tree(fn))
    return trees


@pytest.mark.parametrize(
    ("raw", "expected_prefix"),
    [
        ("heat shock", "3 studies matched heat shock"),
        ("x" * 400, "3 studies matched"),
    ],
)
def test_a_summary_that_echoes_the_user_stays_within_the_limit(
    raw: str,
    expected_prefix: str,
) -> None:
    line = truncate_summary(f"3 studies matched {raw}")
    assert line.startswith(expected_prefix)
    assert len(line) <= 120
