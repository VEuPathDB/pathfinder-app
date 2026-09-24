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
import veupathdb
from veupathdb_mcp.wdk import describe_step_refusal

from pathfinder.ai.agents.execution import _EXECUTION_INSTRUCTIONS
from pathfinder.ai.agents.frame import _FRAME_INSTRUCTIONS
from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS
from pathfinder.ai.agents.vocabulary import USER_FACING_VOCABULARY
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS

_PATHFINDER = Path(__file__).resolve().parents[2]
_CLIENT = Path(veupathdb.__file__).parent

_INTERNAL = re.compile(r"\b(EDA|WDK|FRAME|BUILD|VERIFY|sub-agent|ledger)\b")

# A tool or parameter name, or a study, entity or variable id.
_NAME_OR_ID = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b|\b(?:DS|EDAUD|STUDY|ENT|VAR)_")

_SUMMARY_BUILDERS = frozenset({"with_summary", "summary_chunks"})
_REFUSALS = frozenset({"ModelRetry", "ToolErrorPayload"})
_TITLE_KEYWORDS = frozenset({"title", "detail"})
_RETRY_KEYWORDS = frozenset({"retry"})

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


def _eda_sources() -> list[Path]:
    """Every module that writes a study's refusal, its error or its guidance."""
    return sorted(
        [
            *_PATHFINDER.glob("ai/tools/standalone/eda_*.py"),
            *_PATHFINDER.glob("ai/tools/standalone/_eda_*.py"),
            *_PATHFINDER.glob("services/eda/*.py"),
            _PATHFINDER / "services/strategies/_wdk_step_calls.py",
        ]
    )


def _error_sources() -> list[Path]:
    return sorted(
        [
            *(_PATHFINDER / name for name in _ERROR_SOURCES),
            *(_CLIENT / name for name in _CLIENT_ERROR_SOURCES),
            *_eda_sources(),
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


def _texts(
    expr: ast.expr,
    bindings: dict[str, list[ast.expr]],
    seen: frozenset[str] = frozenset(),
) -> list[str]:
    """The constant parts of one message, and of every local it interpolates."""
    if isinstance(expr, ast.Name):
        if expr.id in seen:
            return []
        return [
            text
            for bound in bindings.get(expr.id, [])
            for text in _texts(bound, bindings, seen | {expr.id})
        ]
    if isinstance(expr, ast.Call) and expr.args:
        return _texts(expr.args[0], bindings, seen)
    joined = "".join(
        child.value
        for child in ast.walk(expr)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    )
    interpolated = [
        text
        for child in ast.walk(expr)
        if isinstance(child, ast.FormattedValue) and isinstance(child.value, ast.Name)
        for text in _texts(child.value, bindings, seen)
    ]
    return [joined, *interpolated] if joined else interpolated


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


def _keyword_texts(path: Path, keywords: frozenset[str]) -> list[str]:
    """Every literal one module passes as one of ``keywords``."""
    tree = ast.parse(path.read_text())
    found: list[str] = []
    for scope in _scopes(tree):
        body = _own_body(scope)
        bindings = _bindings(body)
        for node in body:
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg in keywords:
                    found.extend(_texts(keyword.value, bindings))
    return found


def _titles(path: Path) -> list[str]:
    """Every ``title=`` and ``detail=`` literal one module writes."""
    return _keyword_texts(path, _TITLE_KEYWORDS)


def _interpolated_title_ids(path: Path) -> list[str]:
    """Every internal id a ``title=`` or ``detail=`` of one module interpolates."""
    tree = ast.parse(path.read_text())
    return [
        f"{path.name}:{node.lineno} {name}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg in _TITLE_KEYWORDS
        for child in ast.walk(keyword.value)
        if isinstance(child, ast.FormattedValue)
        for name in [_interpolated_name(child.value)]
        if name.endswith(_INTERNAL_ID_SUFFIXES)
    ]


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
        for path in _eda_sources()
        for line in [
            *_messages(path, _REFUSALS, argument=0),
            *_raised(path),
            *_keyword_texts(path, _RETRY_KEYWORDS),
        ]
    ]
    assert len(lines) > 10, "the refusal scan reads nothing"
    assert _offending(lines) == []


def test_no_study_error_names_a_tool_or_an_id() -> None:
    """A title or detail reaches the researcher; a retry alone may name a tool."""
    lines = [line for path in _eda_sources() for line in _titles(path)]
    assert len(lines) > 10, "the study error scan reads nothing"
    assert sorted({line for line in lines if _NAME_OR_ID.search(line)}) == []


def test_no_study_error_interpolates_an_id_the_researcher_never_typed() -> None:
    found = sorted(
        {line for path in _eda_sources() for line in _interpolated_title_ids(path)}
    )
    assert found == []


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


# A refusal a site sends, verbatim, as one reached a researcher's screen.
STALE_DATASET_REFUSAL = (
    r"""POST /users/1202189953/steps/440118373/reports/standard -> HTTP 422 """
    r"""(UNSPECIFIED): This step is not runnable for the following reasons: """
    r"""{"keyedErrors":{"bq_right_op_TranscriptRecordClasses_TranscriptRecordClass":"""
    r"""["The step referenced by ID '440118363' is not runnable because: """
    r"""{\n \"keyedErrors\": {\n \"samples_percentile_generic\": """
    r"""[\"At least one parameter that 'samples_percentile_generic' depends on """
    r"""is invalid or missing. Errors: \\n{\\n profileset_generic => Invalid """
    r"""value 'P. falciparum Su Strand Specific RNA Seq data - - Sense'.\\n}\\n\"],"""
    r"""\n \"profileset_generic\": [\"Invalid value """
    r"""'P. falciparum Su Strand Specific RNA Seq data - - Sense'.\"]\n },\n """
    r"""\"validationLevel\": \"RUNNABLE\", \"validationStatus\": \"FAILED\", """
    r"""\"errors\": []\n}"]},"validationLevel":"RUNNABLE","""
    r""""validationStatus":"FAILED","errors":[]}"""
)


def test_a_refusal_a_site_sends_is_read_before_a_researcher_sees_it() -> None:
    """A message assembled at runtime obeys the rule the literal scan enforces.

    The scan above reads source literals. This text is built from an exception,
    so only a runtime assertion covers it.
    """
    read = describe_step_refusal(STALE_DATASET_REFUSAL)

    assert read == (
        "This strategy cannot run. The second input of the step you ran sets "
        "'profileset_generic' to 'P. falciparum Su Strand Specific RNA Seq data "
        "- - Sense', which the site no longer offers. Open that step and choose "
        "a value the site offers now."
    )
    assert _INTERNAL.search(read) is None
