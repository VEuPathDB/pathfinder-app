from __future__ import annotations

import ast
from pathlib import Path


def _text(node: ast.AST) -> str | None:
    match node:
        case ast.Constant(value=str() as text):
            return text
        case ast.JoinedStr(values=parts):
            return "".join(filter(None, map(_text, parts)))
        case _:
            return None


def string_literals(path: Path) -> list[str]:
    return [
        text for node in ast.walk(ast.parse(path.read_text())) if (text := _text(node))
    ]
