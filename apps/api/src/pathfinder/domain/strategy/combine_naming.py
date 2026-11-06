"""The name a combine step carries when no researcher named it."""

from __future__ import annotations

from collections.abc import Mapping

from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep

from pathfinder.domain.strategy.step_naming import cut_on_a_word

_LABELS: dict[CombineOp, str] = {
    CombineOp.INTERSECT: "Intersect",
    CombineOp.UNION: "Union",
    CombineOp.MINUS: "Minus",
    CombineOp.RMINUS: "Right minus",
    CombineOp.LONLY: "Left only",
    CombineOp.RONLY: "Right only",
    CombineOp.COLOCATE: "Colocate",
}

_RETIRED = frozenset({"Minus (reversed)", "Colocated"})
"""The labels an earlier release gave, which a stored combine may still carry."""


def combine_display_name(operator: CombineOp) -> str:
    """The label the canvas shows for this operator."""
    return _LABELS[operator]


_GENERATED = frozenset(f"{operator.value} combine".casefold() for operator in CombineOp)
"""The names the canvas once gave a combine it created: "<OPERATOR> combine"."""


def given_by_a_researcher(name: str | None, search_name: str | None) -> bool:
    """Whether a step's name is one a researcher gave it.

    An empty name, an operator's label now or in an earlier release, a generated
    "<OPERATOR> combine" and the search name are defaults: WDK names a step it
    receives without a name after its search.
    """
    if not name:
        return False
    return (
        name != search_name
        and name not in _LABELS.values()
        and name not in _RETIRED
        and name.casefold() not in _GENERATED
    )


def combine_name(
    name: str | None, search_name: str | None, operator: CombineOp | None
) -> str | None:
    """A researcher's name for the combine, else the label of its operator."""
    if operator is None or given_by_a_researcher(name, search_name):
        return name
    return combine_display_name(operator)


def name_the_combines(steps: Mapping[str, StrategyStep]) -> None:
    """Give each combine no researcher named its operator's label, and name each
    nested group no saved strategy names after the steps inside it."""
    for step in steps.values():
        if step.kind is StepKind.COMBINE:
            step.display_name = combine_name(
                step.display_name, step.search_name, step.operator
            )
            if step.expanded_strategy_id is None:
                step.expanded_name = _group_name(steps, step.secondary_input_id)


def _group_name(steps: Mapping[str, StrategyStep], group_id: str | None) -> str | None:
    group = steps.get(group_id) if group_id is not None else None
    if group is None or group.kind is not StepKind.COMBINE:
        return None
    combines: list[StrategyStep] = []
    members: list[StrategyStep] = []
    _gather(steps, group, combines, members)
    shown = cut_on_a_word(", ".join(member.display_label for member in members))
    operators = {combine.operator for combine in combines}
    match list(operators):
        case [CombineOp() as operator]:
            return f"{combine_display_name(operator)}: {shown}"
        case _:
            return shown


def _gather(
    steps: Mapping[str, StrategyStep],
    step: StrategyStep,
    combines: list[StrategyStep],
    members: list[StrategyStep],
) -> None:
    if step.kind is not StepKind.COMBINE:
        members.append(step)
        return
    combines.append(step)
    for input_id in step.input_ids():
        _gather(steps, steps[input_id], combines, members)
