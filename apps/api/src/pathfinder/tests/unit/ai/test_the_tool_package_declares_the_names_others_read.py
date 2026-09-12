"""The names a reader outside the standalone tool package may read of it."""

from __future__ import annotations

import ast
from pathlib import Path
from types import ModuleType

from pathfinder import jobs
from pathfinder.ai import graph, lead

TOOL_PACKAGE = "pathfinder.ai.tools.standalone"


def _package_root(package: ModuleType) -> Path:
    return Path(str(package.__file__)).parent


def _names_a_tool_module(dotted: str) -> bool:
    return dotted == TOOL_PACKAGE or dotted.startswith(f"{TOOL_PACKAGE}.")


def _is_private_module(dotted: str) -> bool:
    tail = dotted.removeprefix(TOOL_PACKAGE).removeprefix(".")
    return any(segment.startswith("_") for segment in tail.split(".") if segment)


def _private_reads(path: Path) -> list[str]:
    """Every private tool name one module reads, written as it is imported."""
    reads: list[str] = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            reads += [
                alias.name
                for alias in node.names
                if _names_a_tool_module(alias.name) and _is_private_module(alias.name)
            ]
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if not _names_a_tool_module(node.module):
                continue
            private_module = _is_private_module(node.module)
            reads += [
                f"{node.module}.{alias.name}"
                for alias in node.names
                if private_module or alias.name.startswith("_")
            ]
    return reads


def _reaches_into_the_tool_package(package: ModuleType) -> list[str]:
    root = _package_root(package)
    return [
        f"{path.relative_to(root.parent)}: {read}"
        for path in sorted(root.rglob("*.py"))
        for read in _private_reads(path)
    ]


def test_the_lead_reads_only_declared_tool_names() -> None:
    """A rename inside the tool package is not an outage in the Lead."""
    assert _reaches_into_the_tool_package(lead) == []


def test_the_graph_reads_only_declared_tool_names() -> None:
    assert _reaches_into_the_tool_package(graph) == []


def test_the_worker_reads_only_declared_tool_names() -> None:
    """A durable job's body names the same surface its agent-side tool does."""
    assert _reaches_into_the_tool_package(jobs) == []


def test_the_guard_walks_every_module_of_the_lead() -> None:
    """A walk that finds no file would pass the two rules above."""
    walked = {path.name for path in _package_root(lead).rglob("*.py")}
    assert {"lead_tools.py", "edit_dispatch.py", "live_state.py"} <= walked


def test_the_guard_walks_every_module_of_the_worker() -> None:
    walked = {path.name for path in _package_root(jobs).rglob("*.py")}
    assert {"optimize_params_impl.py", "eda_compute_impl.py"} <= walked
