"""What changed between two persisted states of one strategy.

A step keeps its id across a write, so the comparison is by step id: a step
present in both is compared parameter by parameter, and one present in only
one of them was added or removed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, walk

from strategist.domain.strategy.expression_handles import stated_text

__all__ = [
    "ParamChange",
    "StepChange",
    "StepSummary",
    "StrategyAstDiff",
    "WeightChange",
    "diff_strategy_asts",
    "nodes_of",
]


class ParamChange(BaseModel):
    """One parameter's value on both sides, in the form it is stated."""

    model_config = ConfigDict(frozen=True)

    name: str
    before: str | None = None
    after: str | None = None


class WeightChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    before: int | None = None
    after: int | None = None


class StepSummary(BaseModel):
    """A step named by its id and the label the user reads."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    label: str


class StepChange(BaseModel):
    """One step whose search or parameters moved."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    label: str
    search_before: str | None = None
    search_after: str | None = None
    params: list[ParamChange] = Field(default_factory=list)
    weight: WeightChange | None = None


class StrategyAstDiff(BaseModel):
    model_config = ConfigDict(frozen=True)

    changed: list[StepChange] = Field(default_factory=list)
    added: list[StepSummary] = Field(default_factory=list)
    removed: list[StepSummary] = Field(default_factory=list)

    @property
    def moved(self) -> bool:
        return bool(self.changed or self.added or self.removed)


def nodes_of(ast: StrategyAst | None) -> dict[str, StrategyStepNode]:
    """Every step of a tree by id, the detached components included."""
    if ast is None:
        return {}
    walked = list(walk(ast.root))
    for detached in ast.detached_roots:
        walked.extend(walk(detached))
    return {node.id: node for node in walked}


def _param_changes(
    before: StrategyStepNode,
    after: StrategyStepNode,
) -> list[ParamChange]:
    return [
        ParamChange(
            name=name,
            before=_stated(before, name),
            after=_stated(after, name),
        )
        for name in sorted(before.parameters.keys() | after.parameters.keys())
        if before.parameters.get(name) != after.parameters.get(name)
    ]


def _stated(node: StrategyStepNode, name: str) -> str | None:
    value = node.parameters.get(name)
    return None if value is None else stated_text(name, value)


def _step_change(
    before: StrategyStepNode,
    after: StrategyStepNode,
) -> StepChange | None:
    params = _param_changes(before, after)
    searches_differ = before.search_name != after.search_name
    weight = (
        None
        if before.wdk_weight == after.wdk_weight
        else WeightChange(before=before.wdk_weight, after=after.wdk_weight)
    )
    if not params and not searches_differ and weight is None:
        return None
    return StepChange(
        step_id=after.id,
        label=after.display_label,
        search_before=before.search_name if searches_differ else None,
        search_after=after.search_name if searches_differ else None,
        params=params,
        weight=weight,
    )


def _summary(node: StrategyStepNode) -> StepSummary:
    return StepSummary(step_id=node.id, label=node.display_label)


def diff_strategy_asts(
    before: StrategyAst | None,
    after: StrategyAst | None,
) -> StrategyAstDiff:
    """Compare two states of one strategy. A missing side moved nothing."""
    if before is None or after is None:
        return StrategyAstDiff()
    old = nodes_of(before)
    new = nodes_of(after)
    changes = [
        change
        for step_id, node in new.items()
        if step_id in old and (change := _step_change(old[step_id], node)) is not None
    ]
    return StrategyAstDiff(
        changed=changes,
        added=[_summary(node) for step_id, node in new.items() if step_id not in old],
        removed=[_summary(node) for step_id, node in old.items() if step_id not in new],
    )
