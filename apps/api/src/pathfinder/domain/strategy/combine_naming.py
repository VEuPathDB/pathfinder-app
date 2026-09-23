"""The name a combine step carries when no researcher named it."""

from __future__ import annotations

from collections.abc import Iterable

from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep

_LABELS: dict[CombineOp, str] = {
    CombineOp.INTERSECT: "Intersect",
    CombineOp.UNION: "Union",
    CombineOp.MINUS: "Minus",
    CombineOp.RMINUS: "Minus (reversed)",
    CombineOp.LONLY: "Left only",
    CombineOp.RONLY: "Right only",
    CombineOp.COLOCATE: "Colocated",
}


def combine_display_name(operator: CombineOp) -> str:
    """The label the canvas shows for this operator."""
    return _LABELS[operator]


_GENERATED = frozenset(f"{operator.value} combine".casefold() for operator in CombineOp)
"""The names the canvas once gave a combine it created: "<OPERATOR> combine"."""


def given_by_a_researcher(name: str | None, search_name: str | None) -> bool:
    """Whether a step's name is one a researcher gave it.

    An empty name, an operator's label, a generated "<OPERATOR> combine" and the
    search name are defaults: WDK names a step it receives without a name after
    its search.
    """
    if not name:
        return False
    return (
        name != search_name
        and name not in _LABELS.values()
        and name.casefold() not in _GENERATED
    )


def combine_name(
    name: str | None, search_name: str | None, operator: CombineOp | None
) -> str | None:
    """A researcher's name for the combine, else the label of its operator."""
    if operator is None or given_by_a_researcher(name, search_name):
        return name
    return combine_display_name(operator)


def name_the_combines(steps: Iterable[StrategyStep]) -> None:
    """Give each combine no researcher named its operator's label."""
    for step in steps:
        if step.kind is StepKind.COMBINE:
            step.display_name = combine_name(
                step.display_name, step.search_name, step.operator
            )
