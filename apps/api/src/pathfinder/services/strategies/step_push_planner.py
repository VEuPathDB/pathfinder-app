from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Discriminator
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, walk


class SkipAction(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["skip"] = "skip"


class CreateAction(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["create"] = "create"


class PatchAction(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["patch"] = "patch"


class RecreateAction(BaseModel):
    model_config = ConfigDict(frozen=True)
    kind: Literal["recreate"] = "recreate"


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


def _topology_tuples(ast: StrategyAst) -> set[tuple[str, str | None, str | None]]:
    return {(s.id, s.primary_input_id, s.secondary_input_id) for s in walk(ast.root)}


def topology_changed(old_ast: StrategyAst | None, new_ast: StrategyAst) -> bool:
    if old_ast is None:
        return True
    return _topology_tuples(old_ast) != _topology_tuples(new_ast)


def _decide_combine(
    new_step: StrategyStepNode, old_step: StrategyStepNode
) -> tuple[StepActionT, str]:
    if new_step.operator != old_step.operator:
        return (
            RecreateAction(),
            f"combine operator changed {old_step.operator}->{new_step.operator}",
        )
    if new_step.input_ids() != old_step.input_ids():
        return RecreateAction(), "combine input topology changed"
    if new_step.colocation_params != old_step.colocation_params:
        return RecreateAction(), "colocation params changed"
    if (
        new_step.display_name != old_step.display_name
        or new_step.wdk_weight != old_step.wdk_weight
    ):
        return PatchAction(), "combine metadata changed"
    return SkipAction(), "combine unchanged"


def _decide_leaf_or_transform(
    new_step: StrategyStepNode, old_step: StrategyStepNode
) -> tuple[StepActionT, str]:
    if new_step.search_name != old_step.search_name:
        return PatchAction(), "search changed"
    if dict(new_step.parameters) != dict(old_step.parameters):
        return PatchAction(), "params changed"
    if new_step.display_name != old_step.display_name:
        return PatchAction(), "display name changed"
    if new_step.wdk_weight != old_step.wdk_weight:
        return PatchAction(), "wdk weight changed"
    if new_step.primary_input_id != old_step.primary_input_id:
        return RecreateAction(), "transform input changed"
    return SkipAction(), "leaf/transform unchanged"


def _decide_step(
    step: StrategyStepNode,
    old_ast: StrategyAst | None,
    old_by_id: dict[str, StrategyStepNode],
    existing_wdk_ids: dict[str, int],
) -> tuple[StepActionT, str]:
    if step.id not in existing_wdk_ids:
        return CreateAction(), "no wdk id"
    if old_ast is None:
        return CreateAction(), "no prior ast"
    old_step = old_by_id.get(step.id)
    if old_step is None:
        return CreateAction(), "new step not in prior ast"
    new_kind = step.infer_kind()
    old_kind = old_step.infer_kind()
    if new_kind != old_kind:
        return RecreateAction(), f"step kind changed {old_kind}->{new_kind}"
    if new_kind == "combine":
        return _decide_combine(step, old_step)
    return _decide_leaf_or_transform(step, old_step)


def plan_step_pushes(
    *,
    old_ast: StrategyAst | None,
    new_ast: StrategyAst,
    existing_wdk_ids: dict[str, int],
) -> list[StepPushPlan]:
    new_steps = walk(new_ast.root)
    old_by_id: dict[str, StrategyStepNode] = (
        _index_by_id(old_ast) if old_ast is not None else {}
    )

    decisions: dict[str, tuple[StepActionT, str]] = {
        step.id: _decide_step(step, old_ast, old_by_id, existing_wdk_ids)
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
            step_id=step.id, action=decisions[step.id][0], reason=decisions[step.id][1]
        )
        for step in new_steps
    ]
