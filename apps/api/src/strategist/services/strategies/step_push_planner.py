from collections.abc import Container, Mapping
from dataclasses import dataclass, field
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator, model_validator
from veupathdb.domain.parameters import ParamValue, same_param_value, value_kind
from veupathdb.domain.strategy import (
    StepSettings,
    StrategyAst,
    StrategyStepNode,
    settings_of,
    walk,
)


class SkipAction(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["skip"] = "skip"

    @property
    def writes_parameters(self) -> bool:
        return False


class CreateAction(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["create"] = "create"

    @property
    def writes_parameters(self) -> bool:
        return True


class PatchAction(BaseModel):
    """A write to a step WDK already holds, naming the parts that moved.

    The search config carries every parameter, the weight and the filters, so
    it is sent only when one of them moved; a new name alone is a properties patch.
    """

    model_config = ConfigDict(frozen=True)
    kind: Literal["patch"] = "patch"
    search_config: bool
    name: bool

    @property
    def writes_parameters(self) -> bool:
        return self.search_config

    @model_validator(mode="after")
    def _writes_something(self) -> PatchAction:
        if not (self.search_config or self.name):
            msg = "a patch that writes nothing is a skip"
            raise ValueError(msg)
        return self


class RecreateAction(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["recreate"] = "recreate"

    @property
    def writes_parameters(self) -> bool:
        return True


StepActionT = Annotated[
    SkipAction | CreateAction | PatchAction | RecreateAction,
    Discriminator("kind"),
]


class StepPushPlan(BaseModel):
    model_config = ConfigDict(frozen=True)
    step_id: str
    action: StepActionT
    reason: str


def _index_by_id(ast: StrategyAst) -> dict[str, StrategyStepNode]:
    return {s.id: s for s in walk(ast.root)}


_RECREATES_A_COMBINE = ("operator", "colocation_params", "wdk_weight", "filters")
_WRITES_A_SEARCH_CONFIG = ("parameters", "wdk_weight", "filters")


@dataclass(frozen=True)
class TurnBaseline:
    started: StepSettings
    replaced: StepSettings | None = None
    explicit: frozenset[str] = frozenset()

    def stale_value(self, name: str, value: ParamValue) -> bool:
        """Whether ``value`` is the turn's copy of one a site fold replaced."""
        if self.replaced is None or name in self.explicit:
            return False
        held = self.replaced.parameters.get(name)
        return held is not None and _same(name, value, held)

    def stale_setting(self, name: str, now: StepSettings) -> bool:
        return self.replaced is not None and name not in self.replaced.changed(now)


@dataclass(frozen=True)
class TheTurn:
    unfinished: Container[str] = frozenset()
    replaced: Mapping[str, StepSettings] = field(default_factory=dict)
    explicit: Mapping[str, frozenset[str]] = field(default_factory=dict)

    def baseline(
        self, step_id: str, old: StrategyStepNode | None
    ) -> TurnBaseline | None:
        if old is None or step_id in self.unfinished:
            return None
        return TurnBaseline(
            started=settings_of(old),
            replaced=self.replaced.get(step_id),
            explicit=self.explicit.get(step_id, frozenset()),
        )


def _same(name: str, left: ParamValue, right: ParamValue) -> bool:
    return same_param_value(name, value_kind(left) or value_kind(right), left, right)


def turn_moved(now: StepSettings, base: TurnBaseline) -> frozenset[str]:
    was = base.started.parameters
    params = {
        name
        for name, value in now.parameters.items()
        if (name not in was or not _same(name, value, was[name]))
        and not base.stale_value(name, value)
    } | {name for name in was if name not in now.parameters}
    settings = {
        name
        for name in now.changed(base.started)
        if name != "parameters" and not base.stale_setting(name, now)
    }
    return frozenset({*settings, *params, *(["parameters"] if params else [])})


def moved_by_the_turn(
    stated: StepSettings, held: StepSettings, base: TurnBaseline | None
) -> list[str]:
    moved = stated.changed(held)
    if base is None:
        return moved
    turned = turn_moved(stated, base)
    return [name for name in moved if name in turned]


def _decide_combine(
    new_step: StrategyStepNode,
    old_step: StrategyStepNode,
    held: StepSettings,
    started: TurnBaseline | None,
) -> tuple[StepActionT, str]:
    if new_step.input_ids() != old_step.input_ids():
        return RecreateAction(), "combine input topology changed"
    moved = moved_by_the_turn(settings_of(new_step), held, started)
    recreated = [name for name in moved if name in _RECREATES_A_COMBINE]
    if recreated:
        return RecreateAction(), "combine " + " and ".join(recreated) + " changed"
    if _renamed(new_step, old_step) or (
        bool(new_step.expanded_name) and "expanded_name" in moved
    ):
        return PatchAction(search_config=False, name=True), "combine name changed"
    return SkipAction(), "combine unchanged"


def _decide_leaf_or_transform(
    new_step: StrategyStepNode,
    old_step: StrategyStepNode,
    held: StepSettings,
    started: TurnBaseline | None,
) -> tuple[StepActionT, str]:
    moved = moved_by_the_turn(settings_of(new_step), held, started)
    if "search_name" in moved:
        return RecreateAction(), "search changed"
    if new_step.primary_input_id != old_step.primary_input_id:
        return RecreateAction(), "transform input changed"
    written = [name for name in moved if name in _WRITES_A_SEARCH_CONFIG]
    renamed = _renamed(new_step, old_step)
    if not written and not renamed:
        return SkipAction(), "leaf/transform unchanged"
    patch = PatchAction(search_config=bool(written), name=renamed)
    return patch, " and ".join([*written, *(["display name"] if renamed else [])]) + (
        " changed"
    )


def _renamed(new_step: StrategyStepNode, old_step: StrategyStepNode) -> bool:
    """A name WDK can be sent: a step whose name was cleared keeps the site's."""
    return (
        bool(new_step.display_name) and new_step.display_name != old_step.display_name
    )


def _decide_step(
    step: StrategyStepNode,
    old_by_id: dict[str, StrategyStepNode],
    existing_wdk_ids: dict[str, int],
    held: Mapping[str, StepSettings],
    turn: TheTurn,
) -> tuple[StepActionT, str]:
    if step.id not in existing_wdk_ids:
        return CreateAction(), "no wdk id"
    old_step = old_by_id.get(step.id)
    holds = held.get(step.id)
    if old_step is None or holds is None:
        return CreateAction(), "no prior step or no read of what wdk holds"
    new_kind = step.infer_kind()
    old_kind = old_step.infer_kind()
    if new_kind != old_kind:
        return RecreateAction(), f"step kind changed {old_kind}->{new_kind}"
    started = turn.baseline(step.id, old_step)
    if new_kind == "combine":
        return _decide_combine(step, old_step, holds, started)
    return _decide_leaf_or_transform(step, old_step, holds, started)


def plan_step_pushes(
    *,
    old_ast: StrategyAst | None,
    new_ast: StrategyAst,
    existing_wdk_ids: dict[str, int],
    held: Mapping[str, StepSettings],
    turn: TheTurn,
) -> list[StepPushPlan]:
    new_steps = walk(new_ast.root)
    old_by_id: dict[str, StrategyStepNode] = (
        _index_by_id(old_ast) if old_ast is not None else {}
    )

    decisions: dict[str, tuple[StepActionT, str]] = {
        step.id: _decide_step(step, old_by_id, existing_wdk_ids, held, turn)
        for step in new_steps
    }

    children: dict[str, list[str]] = {s.id: s.input_ids() for s in new_steps}

    def needs_recreate_due_to_descendant(step: StrategyStepNode) -> bool:
        for child_id in children.get(step.id, []):
            child_decision = decisions.get(child_id)
            if child_decision is None:
                continue
            if isinstance(child_decision[0], (RecreateAction, CreateAction)):
                return True
        return False

    # walk returns leaves first, so ancestors come after descendants.
    for step in new_steps:
        action, _ = decisions[step.id]
        if isinstance(
            action, (SkipAction, PatchAction)
        ) and needs_recreate_due_to_descendant(step):
            decisions[step.id] = (RecreateAction(), "descendant recreated")

    return [
        StepPushPlan(
            step_id=step.id,
            action=decisions[step.id][0],
            reason=decisions[step.id][1],
        )
        for step in new_steps
    ]
