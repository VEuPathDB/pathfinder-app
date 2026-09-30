"""No PathFinder tool sets ``ToolReturn.content``.

pydantic-ai sends that field to the model as a separate user prompt part, so
text a tool writes there reads as the researcher's own message. A tool returns
data only; what the Lead does with a result is in its instructions.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pathfinder

_PACKAGE = Path(pathfinder.__file__).parent


def _modules() -> list[Path]:
    tests = _PACKAGE / "tests"
    return [path for path in _PACKAGE.rglob("*.py") if tests not in path.parents]


def _content_writes(tree: ast.AST) -> list[int]:
    """The lines that construct a ToolReturn with content or assign ``.content``."""
    lines: list[int] = []
    for node in ast.walk(tree):
        match node:
            case ast.Call(
                func=ast.Name(id="ToolReturn") | ast.Attribute(attr="ToolReturn"),
                keywords=keywords,
            ) if any(keyword.arg == "content" for keyword in keywords):
                lines.append(node.lineno)
            case ast.Assign(targets=targets) if any(
                isinstance(target, ast.Attribute) and target.attr == "content"
                for target in targets
            ):
                lines.append(node.lineno)
            case _:
                pass
    return lines


def test_the_scan_reads_the_tool_modules() -> None:
    names = {path.name for path in _modules()}

    assert {"variant_comparison.py", "scored_comparison.py", "lead_consult.py"} <= names


def test_the_scan_finds_a_content_write() -> None:
    written = ast.parse(
        "ran = with_summary(value, 'line', ctx=ctx)\n"
        "ran.content = 'Summarize the trade-off for the user'\n"
        "ToolReturn(return_value=value, content='ask which to proceed with')\n"
        "messages.ToolReturn(return_value=value, content='proceed with it')\n"
    )

    assert _content_writes(written) == [2, 3, 4]


def test_no_tool_sets_the_content_the_model_reads_as_a_user_message() -> None:
    found = {
        str(path.relative_to(_PACKAGE)): lines
        for path in _modules()
        if (lines := _content_writes(ast.parse(path.read_text())))
    }

    assert found == {}
