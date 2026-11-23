from __future__ import annotations

import ast
from pathlib import Path

_STRATEGIST = Path(__file__).resolve().parents[4]
_THE_RENAME = "ai/tools/standalone/strategy_rename.py"


def _modules_defining_a_rename() -> list[str]:
    found: list[str] = []
    for path in sorted(_STRATEGIST.rglob("*.py")):
        relative = path.relative_to(_STRATEGIST).as_posix()
        if relative.startswith("tests/"):
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            match node:
                case (
                    ast.AsyncFunctionDef(name="rename_strategy")
                    | ast.FunctionDef(name="rename_strategy")
                ):
                    found.append(relative)
    return found


def test_one_module_defines_the_rename_tool() -> None:
    assert _modules_defining_a_rename() == [_THE_RENAME]
