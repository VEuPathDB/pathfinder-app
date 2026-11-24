"""A write that departs from the plan is refused by one conversion, which every
tool that commits runs."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from strategist.ai.tools.standalone.strategy_refusals import departures_refused
from strategist.domain.refusal import Check, Problem, Problems, RefusalKey
from strategist.domain.strategy.operations.apply import PlanDeparturesError
from strategist.platform.refusals import ProblemsRefusal

_AI = Path(__file__).resolve().parents[4] / "ai"
_OWNERS = {
    "tools/standalone/strategy_refusals.py",
    "lead/edit_dispatch.py",
}


def test_a_departure_is_refused_with_every_problem_and_nothing_written() -> None:
    problems = Problems(
        found=(
            Problem(
                key=RefusalKey(check=Check.THE_VALUE_TO_THE_SPEC),
                sentence="c_a states organism 3D7, and the write sends HB3.",
            ),
        )
    )

    with pytest.raises(ProblemsRefusal) as refused, departures_refused():
        raise PlanDeparturesError(problems)

    assert (refused.value.problems, str(refused.value)) == (
        problems,
        "c_a states organism 3D7, and the write sends HB3. Nothing was written.",
    )


def _catches_a_departure(handler: ast.ExceptHandler) -> bool:
    return (
        isinstance(handler.type, ast.Name) and handler.type.id == "PlanDeparturesError"
    )


def test_no_tool_converts_a_departure_on_its_own() -> None:
    found = sorted(
        f"{path.relative_to(_AI)}:{node.lineno}"
        for path in _AI.rglob("*.py")
        if str(path.relative_to(_AI)) not in _OWNERS
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.ExceptHandler) and _catches_a_departure(node)
    )

    assert found == []
