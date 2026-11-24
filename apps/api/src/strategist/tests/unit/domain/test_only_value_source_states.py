from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from veupathdb.domain.parameters import StringValue

from strategist.domain.strategy.operational_spec import BoundValue

_PACKAGE = Path(__file__).resolve().parents[3]
_MINTS = "domain/strategy/value_source.py"
_FIELDS = "domain/strategy/stated_source.py"


def _stated(node: ast.expr | None) -> bool:
    match node:
        case ast.Constant(value="stated"):
            return True
    return False


def _the_source(node: ast.expr | None) -> bool:
    match node:
        case ast.Constant(value="source") | ast.Attribute(attr="source"):
            return True
    return False


def _statings(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        match node:
            case ast.Call(func=ast.Name(id="StatedSource")):
                found.append((node.lineno, "constructs StatedSource"))
            case ast.Call(func=ast.Attribute(attr="sourced"), args=[first, *_]) if (
                _stated(first)
            ):
                found.append((node.lineno, 'calls sourced("stated")'))
            case ast.Call(keywords=keywords) if any(
                k.arg == "source" and _stated(k.value) for k in keywords
            ):
                found.append((node.lineno, 'passes source="stated"'))
            case ast.Dict(keys=keys, values=values) if any(
                _the_source(key) and _stated(value)
                for key, value in zip(keys, values, strict=True)
            ):
                found.append((node.lineno, 'holds {"source": "stated"}'))
            case ast.Assign(targets=targets, value=value) if _stated(value) and any(
                _the_source(t) for t in targets
            ):
                found.append((node.lineno, 'assigns source = "stated"'))
    return found


def _production() -> list[Path]:
    return [
        path
        for path in sorted(_PACKAGE.rglob("*.py"))
        if "tests" not in path.relative_to(_PACKAGE).parts
    ]


def test_only_value_source_makes_a_stated_source() -> None:
    found = {
        f"{path.relative_to(_PACKAGE).as_posix()}:{line}": what
        for path in _production()
        for line, what in _statings(ast.parse(path.read_text()))
    }

    assert sorted({key.split(":")[0] for key in found}) == [_FIELDS, _MINTS], found


@pytest.mark.parametrize(
    "planted",
    [
        "StatedSource(words='Pfam')",
        "held.sourced('stated', 'the message names it')",
        "BoundValue(value=v, source='stated')",
        "held.model_copy(update={'source': 'stated'})",
        "held.source = 'stated'",
    ],
)
def test_a_planted_stated_source_is_found(planted: str) -> None:
    assert [line for line, _ in _statings(ast.parse(planted))] == [1]


@pytest.mark.parametrize("source", ["stated"])
def test_a_bare_stated_source_is_refused(source: Any) -> None:
    held = BoundValue(value=StringValue(value="Pfam"), source="default")

    with pytest.raises(
        ValueError, match="no source a value takes outside value_source"
    ):
        held.sourced(source, "the message names it")
