"""What changed between two persisted states of one strategy.

A step keeps its id across a write, so the comparison is by step id: a step
present in both is compared parameter by parameter, and one present in only
one of them was added or removed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from pathfinder.domain.parameters.value_codec import to_wire
from pathfinder.domain.strategy.ast import StrategyStepNode
from pathfinder.domain.strategy.strategy_ast import StrategyAst
from pathfinder.domain.strategy.tree import walk

__all__ = [
    "ParamChange",
    "StepChange",
    "StepSummary",
    "StrategyAstDiff",
    "diff_strategy_asts",
]


class ParamChange(BaseModel):
    """One parameter's value on both sides, in wire form."""

    model_config = ConfigDict(frozen=True)

    name: str
    before: str | None = None
    after: str | None = None


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


class StrategyAstDiff(BaseModel):
    model_config = ConfigDict(frozen=True)

    changed: list[StepChange] = Field(default_factory=list)
    added: list[StepSummary] = Field(default_factory=list)
    removed: list[StepSummary] = Field(default_factory=list)

    @property
    def moved(self) -> bool:
        return bool(self.changed or self.added or self.removed)


def _nodes(ast: StrategyAst | None) -> dict[str, StrategyStepNode]:
    if ast is None:
        return {}
    walked = list(walk(ast.root))
    for detached in ast.detached_roots:
        walked.extend(walk(detached))
    return {node.id: node for node in walked}


def _wire_params(node: StrategyStepNode) -> dict[str, str]:
    return {name: to_wire(value) for name, value in node.parameters.items()}


def _param_changes(
    before: StrategyStepNode,
    after: StrategyStepNode,
) -> list[ParamChange]:
    old = _wire_params(before)
    new = _wire_params(after)
    return [
        ParamChange(name=name, before=old.get(name), after=new.get(name))
        for name in sorted(old.keys() | new.keys())
        if old.get(name) != new.get(name)
    ]


def _step_change(
    before: StrategyStepNode,
    after: StrategyStepNode,
) -> StepChange | None:
    params = _param_changes(before, after)
    searches_differ = before.search_name != after.search_name
    if not params and not searches_differ:
        return None
    return StepChange(
        step_id=after.id,
        label=after.display_label,
        search_before=before.search_name if searches_differ else None,
        search_after=after.search_name if searches_differ else None,
        params=params,
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
    old = _nodes(before)
    new = _nodes(after)
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
