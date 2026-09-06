"""No string a researcher can read names PathFinder's internals.

The glossary is `docs/knowledge/decisions/user-facing-vocabulary.md`. A tool
summary, an error title or detail, and a refusal that can reach a
`tool-output-error` all obey it. Guidance meant only for the model may still
name a tool.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from pathfinder.ai.agents.execution import _EXECUTION_INSTRUCTIONS
from pathfinder.ai.agents.frame import _FRAME_INSTRUCTIONS
from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS
from pathfinder.ai.agents.vocabulary import USER_FACING_VOCABULARY
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS

_PATHFINDER = Path(__file__).resolve().parents[2]
_CLIENT = _PATHFINDER.parents[3] / "veupathdb-py" / "src" / "veupathdb"

_INTERNAL = re.compile(r"\b(EDA|WDK|FRAME|BUILD|VERIFY|sub-agent|ledger)\b")

_SUMMARY_BUILDERS = frozenset({"with_summary", "summary_chunks"})
_REFUSALS = frozenset({"ModelRetry", "ToolErrorPayload"})
_TITLE_KEYWORDS = frozenset({"title", "detail"})

_ERROR_SOURCES = ("platform/errors.py",)
_CLIENT_ERROR_SOURCES = ("eda/errors.py", "errors.py")

# An id the researcher never typed. A step id is their own step, so it stays.
_INTERNAL_ID_SUFFIXES = (
    "dataset_id",
    "entity_id",
    "variable_id",
    "study_id",
    "wdk_strategy_id",
)


def _sources() -> list[Path]:
    """Every module of the application, tests excluded."""
    return [
        path
        for path in sorted(_PATHFINDER.rglob("*.py"))
        if "tests" not in path.relative_to(_PATHFINDER).parts
    ]


def _refusal_sources() -> list[Path]:
    return sorted(
        [
            *_PATHFINDER.glob("ai/tools/standalone/eda_*.py"),
            *_PATHFINDER.glob("services/eda/*.py"),
        ]
    )


def _error_sources() -> list[Path]:
    return sorted(
        [
            *(_PATHFINDER / name for name in _ERROR_SOURCES),
            *(_CLIENT / name for name in _CLIENT_ERROR_SOURCES),
            *_PATHFINDER.glob("services/eda/*.py"),
        ]
    )


def _called(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _own_body(node: ast.AST) -> list[ast.AST]:
    """Every node of one scope, skipping the functions nested inside it."""
    nested = {
        inner
        for child in ast.iter_child_nodes(node)
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        for inner in ast.walk(child)
    }
    return [
        child for child in ast.walk(node) if child is not node and child not in nested
    ]


def _bindings(body: list[ast.AST]) -> dict[str, list[ast.expr]]:
    found: dict[str, list[ast.expr]] = {}
    for node in body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                found.setdefault(target.id, []).append(node.value)
    return found


def _texts(expr: ast.expr, bindings: dict[str, list[ast.expr]]) -> list[str]:
    """The constant parts of one message, with its interpolations removed."""
    if isinstance(expr, ast.Name):
        return [
            text
            for bound in bindings.get(expr.id, [])
            for text in _texts(bound, bindings)
        ]
    if isinstance(expr, ast.Call) and expr.args:
        return _texts(expr.args[0], bindings)
    joined = "".join(
        child.value
        for child in ast.walk(expr)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    )
    return [joined] if joined else []


def _scopes(tree: ast.Module) -> list[ast.AST]:
    return [
        tree,
        *[
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ],
    ]


def _messages(path: Path, names: frozenset[str], *, argument: int) -> list[str]:
    """Every literal message a call of one of ``names`` carries."""
    tree = ast.parse(path.read_text())
    found: list[str] = []
    for scope in _scopes(tree):
        body = _own_body(scope)
        bindings = _bindings(body)
        for node in body:
            if not isinstance(node, ast.Call) or _called(node) not in names:
                continue
            if len(node.args) <= argument:
                continue
            found.extend(_texts(node.args[argument], bindings))
    return found


def _raised(path: Path) -> list[str]:
    """Every literal detail a raised refusal of one module carries."""
    tree = ast.parse(path.read_text())
    found: list[str] = []
    for scope in _scopes(tree):
        body = _own_body(scope)
        bindings = _bindings(body)
        for node in body:
            if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call):
                continue
            if node.exc.args:
                found.extend(_texts(node.exc.args[0], bindings))
    return found


def _titles(path: Path) -> list[str]:
    """Every ``title=`` and ``detail=`` literal one module writes."""
    tree = ast.parse(path.read_text())
    found: list[str] = []
    for scope in _scopes(tree):
        body = _own_body(scope)
        bindings = _bindings(body)
        for node in body:
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg in _TITLE_KEYWORDS:
                    found.extend(_texts(keyword.value, bindings))
    return found


def _interpolated_name(expr: ast.expr) -> str:
    """The name an interpolation reads, at the end of whatever path reaches it."""
    if isinstance(expr, ast.Attribute):
        return expr.attr
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Subscript):
        return _interpolated_name(expr.value)
    if isinstance(expr, ast.Call):
        return _interpolated_name(expr.func)
    return ""


def _interpolated_ids(path: Path) -> list[str]:
    """Every internal id a summary of one module writes into its line."""
    tree = ast.parse(path.read_text())
    found: list[str] = []
    for scope in _scopes(tree):
        body = _own_body(scope)
        for node in body:
            if not isinstance(node, ast.Call) or _called(node) not in _SUMMARY_BUILDERS:
                continue
            if len(node.args) < 2:
                continue
            for child in ast.walk(node.args[1]):
                if not isinstance(child, ast.FormattedValue):
                    continue
                name = _interpolated_name(child.value)
                if name.endswith("step_id"):
                    continue
                if name.endswith(_INTERNAL_ID_SUFFIXES):
                    found.append(f"{path.name}:{node.lineno} {name}")
    return found


def _offending(lines: list[str]) -> list[str]:
    return sorted({line for line in lines if _INTERNAL.search(line)})


def test_no_tool_summary_names_an_internal_word() -> None:
    lines = [
        line
        for path in _sources()
        for line in _messages(path, _SUMMARY_BUILDERS, argument=1)
    ]
    assert len(lines) > 60, "the summary scan reads nothing"
    assert _offending(lines) == []


def test_no_error_title_or_detail_names_an_internal_word() -> None:
    lines = [line for path in _error_sources() for line in _titles(path)]
    assert len(lines) > 40, "the error scan reads nothing"
    assert _offending(lines) == []


def test_no_study_refusal_names_an_internal_word() -> None:
    lines = [
        line
        for path in _refusal_sources()
        for line in [*_messages(path, _REFUSALS, argument=0), *_raised(path)]
    ]
    assert len(lines) > 10, "the refusal scan reads nothing"
    assert _offending(lines) == []


def test_no_summary_writes_an_id_the_researcher_never_typed() -> None:
    """A line names the study, not the dataset the study came from."""
    found = sorted({line for path in _sources() for line in _interpolated_ids(path)})
    assert found == []


def test_the_rule_names_the_words_and_their_replacements() -> None:
    text = " ".join(USER_FACING_VOCABULARY.split())
    for word in ("EDA", "WDK", "FRAME", "BUILD", "VERIFY", "sub-agent", "Ledger"):
        assert f"{word}," in text, word
    assert "``DS_``/``ENT_``/``VAR_`` id" in text
    assert "study, search, strategy, step, sample, gene and plan" in text
    assert "digest's prose, key findings, caveats and reason" in text


@pytest.mark.parametrize(
    ("role", "instructions"),
    [
        ("lead", LEAD_INSTRUCTIONS),
        ("frame", _FRAME_INSTRUCTIONS),
        ("execution", _EXECUTION_INSTRUCTIONS),
        ("verification", _VERIFICATION_INSTRUCTIONS),
    ],
)
def test_every_agent_that_writes_for_a_reader_carries_the_rule(
    role: str,
    instructions: str,
) -> None:
    """Recovery runs on the execution agent, so four surfaces cover five roles."""
    assert USER_FACING_VOCABULARY in instructions, role
