"""Properties of PathFinder's own tree that no import contract can see.

The WDK connection, the ``current`` alias and the site vocabulary belong to the
client library, and the semantic index to the MCP server. What is read here is
that this application never reproduces them.
"""

from __future__ import annotations

import ast
import importlib.util
from dataclasses import dataclass
from functools import cache
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_SITE_SOURCES = ("get_site", "SiteInfo", "service_url")
_CURRENT_ALIAS = "/users/current"
_RESOLVERS = ("services/wdk_identity.py",)


@dataclass(frozen=True)
class _CallSite:
    module: str
    line: int
    detail: str


@cache
def _modules() -> tuple[tuple[str, str], ...]:
    return tuple(
        (path.relative_to(_SOURCE_ROOT).as_posix(), path.read_text())
        for path in _SOURCE_ROOT.rglob("*.py")
        if "tests/" not in path.relative_to(_SOURCE_ROOT).as_posix()
    )


def _modules_containing(needle: str) -> list[str]:
    return [module for module, source in _modules() if needle in source]


def _is_httpx_client(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr in {"AsyncClient", "Client"}
        and isinstance(func.value, ast.Name)
        and func.value.id == "httpx"
    )


def _site_backed_clients(module: str, source: str) -> list[_CallSite]:
    """Every httpx client whose base url is resolved from the site router."""
    found: list[_CallSite] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not _is_httpx_client(node):
            continue
        for keyword in node.keywords:
            if keyword.arg != "base_url":
                continue
            expression = ast.unparse(keyword.value)
            if any(name in expression for name in _SITE_SOURCES):
                found.append(_CallSite(module, node.lineno, expression))
    return found


def _docstrings(tree: ast.AST) -> set[int]:
    """The id of every string node that is a docstring rather than a value."""
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, holders) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            found.add(id(first.value))
    return found


def _current_alias_literals(module: str, source: str) -> list[_CallSite]:
    """Every string value naming the ``current`` alias, docstrings excluded."""
    tree = ast.parse(source)
    prose = _docstrings(tree)
    return [
        _CallSite(module, node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and _CURRENT_ALIAS in node.value
        and id(node) not in prose
    ]


def test_wdk_map_005_no_pathfinder_module_builds_a_site_client() -> None:
    offenders = [
        site
        for module, source in _modules()
        for site in _site_backed_clients(module, source)
    ]

    assert offenders == []


def test_wdk_http_001_only_the_resolver_names_the_current_alias() -> None:
    offenders = [
        site
        for module, source in _modules()
        if module not in _RESOLVERS
        for site in _current_alias_literals(module, source)
    ]

    assert offenders == []


def test_wdk_valid_007_no_level_is_ever_sent_to_wdk() -> None:
    """A level that is legal in the model can be fatal on the way out."""
    assert _modules_containing("validationLevel") == []


def test_the_semantic_index_is_not_this_applications_to_declare() -> None:
    """The index ships with the MCP server; this tree holds no copy of it."""
    spec = importlib.util.find_spec("veupathdb_mcp.embeddings.semantic_index")

    assert spec is not None
    assert spec.origin is not None
    assert not Path(spec.origin).is_relative_to(_SOURCE_ROOT)
