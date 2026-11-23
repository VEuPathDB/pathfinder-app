from __future__ import annotations

import ast
from pathlib import Path

_PRODUCTION = Path(__file__).resolve().parents[3]


def _a_text_check(keyword: ast.keyword) -> bool:
    match keyword:
        case ast.keyword(arg="check", value=ast.Constant()):
            return True
        case _:
            return False


def _texts_named_as_checks() -> list[str]:
    found: list[str] = []
    for path in sorted(_PRODUCTION.rglob("*.py")):
        if "tests" in path.relative_to(_PRODUCTION).parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            match node:
                case ast.Call(func=ast.Name(id="RefusalKey"), keywords=keywords):
                    found += [
                        f"{path.relative_to(_PRODUCTION)}:{node.lineno}"
                        for keyword in keywords
                        if _a_text_check(keyword)
                    ]
                case _:
                    continue
    return found


def test_no_production_key_names_its_check_in_free_text() -> None:
    assert _texts_named_as_checks() == []
