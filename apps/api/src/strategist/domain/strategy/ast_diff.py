"""What changed between two persisted states of one strategy.

A step keeps its id across a write, so the comparison is by step id: a step
present in both is compared setting by setting, and one present in only
one of them was added or removed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.strategy import (
    StepSettings,
    StrategyAst,
    StrategyStepNode,
    settings_of,
    walk,
)

from strategist.domain.strategy.expression_handles import stated_text
from strategist.domain.strategy.step_settings_text import OWN_LINES

__all__ = [
    "ParamChange",
    "StepChange",
    "StepSummary",
    "StrategyAstDiff",
    "diff_strategy_asts",
    "nodes_of",
]


class ParamChange(BaseModel):
    """One parameter's value on both sides, in the form it is stated."""

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
    """One step whose search, parameters or other settings moved."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    label: str
    search_before: str | None = None
    search_after: str | None = None
    params: list[ParamChange] = Field(default_factory=list)
    settings: list[str] = Field(default_factory=list)
    before: StepSettings = Field(default_factory=StepSettings)
    after: StepSettings = Field(default_factory=StepSettings)


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
    was, now = settings_of(before), settings_of(after)
    settings = [name for name in was.changed(now) if name not in OWN_LINES]
    if not params and not searches_differ and not settings:
        return None
    return StepChange(
        step_id=after.id,
        label=after.display_label,
        search_before=before.search_name if searches_differ else None,
        search_after=after.search_name if searches_differ else None,
        params=params,
        settings=settings,
        before=was,
        after=now,
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
