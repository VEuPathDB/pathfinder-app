from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Self

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, TypeAdapter, model_validator
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    PhyleticExpression,
    PhyleticTree,
    TaxaCount,
    check_expression,
)
from veupathdb.errors import ParamMessages, ValidationError

from pathfinder.domain.strategy.operational_spec import Criterion

SAMPLED_GROUP_LIMIT = 5

_REFUSED = TypeAdapter(list[ParamMessages])


class ExpressionFit(CamelModel):
    model_config = ConfigDict(frozen=True)

    wdk_step_id: int
    expression: str
    sampled: int = Field(ge=0, le=SAMPLED_GROUP_LIMIT)
    held: int = Field(ge=0)
    failing: list[str] = Field(default_factory=list)
    unmatched: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _each_group_is_judged_once(self) -> Self:
        if self.held + len(self.failing) != self.sampled:
            msg = "an expression fit holds held + failing == sampled"
            raise ValueError(msg)
        if self.unmatched and self.sampled:
            msg = "only a step that holds no group names units that match none"
            raise ValueError(msg)
        return self

    @computed
    def sentence(self) -> str:
        step = f"step {self.wdk_step_id}"
        counts = "on the site's per-genome counts"
        if self.failing:
            verb = "does" if len(self.failing) == 1 else "do"
            return (
                f"{len(self.failing)} of {self.sampled} sampled groups of {step} "
                f"{verb} not meet its phyletic expression {counts}: "
                f"{', '.join(self.failing)}"
            )
        if self.unmatched:
            return (
                f"{step} holds no group, and its phyletic expression matches none "
                f"as the site reads it: {' '.join(self.unmatched)}"
            )
        if not self.sampled:
            return f"{step} holds no group"
        return (
            f"{self.held} of {self.sampled} sampled groups of {step} meet its "
            f"phyletic expression {counts}"
        )


def _matches_no_group(unit: TaxaCount, tree: PhyleticTree) -> bool:
    genomes = sorted(tree.genomes_under(unit.codes))
    groups: list[dict[str, int]]
    if unit.taxa:
        groups = [dict.fromkeys(genomes[:k], 1) for k in range(len(genomes) + 1)]
    else:
        held = range(1, unit.count + 2)
        groups = [{}, *({genome: n} for genome in genomes[:1] for n in held)]
    return not any(unit.holds_for(group, tree) for group in groups)


def _why(unit: TaxaCount, tree: PhyleticTree) -> str:
    try:
        check_expression(PhyleticExpression(root=unit), tree)
    except ValidationError as refused:
        rows = _REFUSED.validate_python(refused.errors or [])
        return " ".join(message for row in rows for message in row.messages)
    return f"{unit.render()} matches no group."


def unmatched_units(expression: PhyleticExpression, tree: PhyleticTree) -> list[str]:
    terms = expression.site_reading().root.operands("OR")
    blocked = [
        [u for u in PhyleticExpression(root=term).units() if _matches_no_group(u, tree)]
        for term in terms
    ]
    if not all(blocked):
        return []
    return [_why(unit, tree) for unit in dict.fromkeys(u for us in blocked for u in us)]


def expression_fit(
    wdk_step_id: int,
    expression: PhyleticExpression,
    groups: Mapping[str, Mapping[str, int]],
    tree: PhyleticTree,
) -> ExpressionFit:
    failing = [
        group
        for group, proteins in groups.items()
        if not expression.holds_for(proteins, tree)
    ]
    return ExpressionFit(
        wdk_step_id=wdk_step_id,
        expression=expression.render(),
        sampled=len(groups),
        held=len(groups) - len(failing),
        failing=failing,
        unmatched=[] if groups else unmatched_units(expression, tree),
    )


def bound_expressions(
    criteria: Sequence[Criterion], wdk_step_ids: Mapping[str, int]
) -> dict[int, str]:
    bound: dict[int, str] = {}
    for criterion in criteria:
        value = criterion.param_values.get(PHYLETIC_EXPRESSION_PARAM)
        if value is None or criterion.id not in wdk_step_ids:
            continue
        try:
            expression = PhyleticExpression.parse(value.to_wire())
        except ValidationError:
            continue
        bound[wdk_step_ids[criterion.id]] = expression.render()
    return bound


def live_fits(
    fits: Sequence[ExpressionFit], bound: Mapping[int, str]
) -> list[ExpressionFit]:
    return [fit for fit in fits if bound.get(fit.wdk_step_id) == fit.expression]


__all__ = [
    "SAMPLED_GROUP_LIMIT",
    "ExpressionFit",
    "bound_expressions",
    "expression_fit",
    "live_fits",
    "unmatched_units",
]
