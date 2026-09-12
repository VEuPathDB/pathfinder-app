from collections.abc import Iterable

from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    StringValue,
)
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.services.strategies.step_push_planner import (
    CreateAction,
    PatchAction,
    RecreateAction,
    SkipAction,
    StepPushPlan,
    plan_step_pushes,
    topology_changed,
)


def _multi(items: Iterable[str]) -> MultiPickValue:
    return MultiPickValue(values=list(items))


def _string(v: str) -> StringValue:
    return StringValue(value=v)


def _leaf(
    step_id: str,
    search: str = "GenesByTaxon",
    **params: ParamValue,
) -> StrategyStepNode:
    return StrategyStepNode(
        search_name=search,
        parameters=dict(params) if params else {"organism": _multi(["Pf3D7"])},
        id=step_id,
    )


def _combine(
    step_id: str,
    primary: StrategyStepNode,
    secondary: StrategyStepNode,
    op: CombineOp = CombineOp.UNION,
    display_name: str | None = None,
) -> StrategyStepNode:
    return StrategyStepNode(
        search_name="__combine__",
        primary_input=primary,
        secondary_input=secondary,
        operator=op,
        display_name=display_name,
        id=step_id,
    )


def _transform(
    step_id: str,
    primary: StrategyStepNode,
    **params: ParamValue,
) -> StrategyStepNode:
    return StrategyStepNode(
        search_name="GenesByOrtholog",
        primary_input=primary,
        parameters=dict(params) if params else {},
        id=step_id,
    )


def _ast(root: StrategyStepNode) -> StrategyAst:
    return StrategyAst(record_type="transcript", root=root)


def _four_step_strategy_with_two_combines() -> StrategyAst:
    a = _leaf("step_a", organism=_multi(["Pf3D7"]))
    b = _leaf("step_b", organism=_multi(["PvP01"]))
    c = _leaf("step_c", organism=_multi(["Pk"]))
    inner = _combine("step_inner", a, b, op=CombineOp.UNION)
    outer = _combine("step_outer", inner, c, op=CombineOp.INTERSECT)
    return _ast(outer)


def test_no_old_ast_creates_all_steps() -> None:
    a = _leaf("step_a")
    b = _leaf("step_b")
    inner = _combine("step_inner", a, b, op=CombineOp.UNION)
    t = _transform("step_t", inner, ortho_pattern=_string("%Pf:Y%"))
    new_ast = _ast(t)

    plan = plan_step_pushes(old_ast=None, new_ast=new_ast, existing_wdk_ids={})

    assert plan == [
        StepPushPlan(step_id="step_a", action=CreateAction(), reason="no wdk id"),
        StepPushPlan(step_id="step_b", action=CreateAction(), reason="no wdk id"),
        StepPushPlan(step_id="step_inner", action=CreateAction(), reason="no wdk id"),
        StepPushPlan(step_id="step_t", action=CreateAction(), reason="no wdk id"),
    ]


def test_unchanged_strategy_skips_everything() -> None:
    ast = _four_step_strategy_with_two_combines()
    wdk_ids = {"step_a": 1, "step_b": 2, "step_c": 3, "step_inner": 4, "step_outer": 5}

    plan = plan_step_pushes(old_ast=ast, new_ast=ast, existing_wdk_ids=wdk_ids)

    assert all(p.action == SkipAction() for p in plan)
    assert {p.step_id for p in plan} == set(wdk_ids.keys())
    assert len(plan) == 5


def test_single_leaf_param_change_patches_only_that_leaf() -> None:
    old = _four_step_strategy_with_two_combines()
    a2 = _leaf("step_a", organism=_multi(["Pf3D7", "Pf7G8"]))
    b = _leaf("step_b", organism=_multi(["PvP01"]))
    c = _leaf("step_c", organism=_multi(["Pk"]))
    inner = _combine("step_inner", a2, b, op=CombineOp.UNION)
    outer = _combine("step_outer", inner, c, op=CombineOp.INTERSECT)
    new = _ast(outer)
    wdk_ids = {"step_a": 1, "step_b": 2, "step_c": 3, "step_inner": 4, "step_outer": 5}

    plan = plan_step_pushes(old_ast=old, new_ast=new, existing_wdk_ids=wdk_ids)

    by_id = {p.step_id: p for p in plan}
    assert by_id["step_a"].action == PatchAction()
    assert by_id["step_a"].reason == "params changed"
    assert by_id["step_b"].action == SkipAction()
    assert by_id["step_c"].action == SkipAction()
    assert by_id["step_inner"].action == SkipAction()
    assert by_id["step_outer"].action == SkipAction()
    counts = {
        type(action).__name__: sum(1 for p in plan if p.action == action)
        for action in (SkipAction(), CreateAction(), PatchAction(), RecreateAction())
    }
    assert counts == {
        "SkipAction": 4,
        "CreateAction": 0,
        "PatchAction": 1,
        "RecreateAction": 0,
    }


def test_combine_operator_change_recreates_only_that_combine() -> None:
    old = _four_step_strategy_with_two_combines()
    a = _leaf("step_a", organism=_multi(["Pf3D7"]))
    b = _leaf("step_b", organism=_multi(["PvP01"]))
    c = _leaf("step_c", organism=_multi(["Pk"]))
    inner = _combine("step_inner", a, b, op=CombineOp.UNION)
    outer = _combine("step_outer", inner, c, op=CombineOp.UNION)
    new = _ast(outer)
    wdk_ids = {"step_a": 1, "step_b": 2, "step_c": 3, "step_inner": 4, "step_outer": 5}

    plan = plan_step_pushes(old_ast=old, new_ast=new, existing_wdk_ids=wdk_ids)

    by_id = {p.step_id: p for p in plan}
    assert by_id["step_outer"].action == RecreateAction()
    assert "operator changed" in by_id["step_outer"].reason
    assert by_id["step_inner"].action == SkipAction()
    assert by_id["step_a"].action == SkipAction()
    assert by_id["step_b"].action == SkipAction()
    assert by_id["step_c"].action == SkipAction()


def test_combine_operator_change_propagates_recreate_upward() -> None:
    old = _four_step_strategy_with_two_combines()
    a = _leaf("step_a", organism=_multi(["Pf3D7"]))
    b = _leaf("step_b", organism=_multi(["PvP01"]))
    c = _leaf("step_c", organism=_multi(["Pk"]))
    inner = _combine("step_inner", a, b, op=CombineOp.INTERSECT)
    outer = _combine("step_outer", inner, c, op=CombineOp.INTERSECT)
    new = _ast(outer)
    wdk_ids = {"step_a": 1, "step_b": 2, "step_c": 3, "step_inner": 4, "step_outer": 5}

    plan = plan_step_pushes(old_ast=old, new_ast=new, existing_wdk_ids=wdk_ids)

    by_id = {p.step_id: p for p in plan}
    assert by_id["step_inner"].action == RecreateAction()
    assert "operator changed" in by_id["step_inner"].reason
    assert by_id["step_outer"].action == RecreateAction()
    assert by_id["step_outer"].reason == "descendant recreated"
    assert by_id["step_a"].action == SkipAction()
    assert by_id["step_b"].action == SkipAction()


def test_combine_input_swap_is_recreate() -> None:
    a = _leaf("step_a", organism=_multi(["Pf3D7"]))
    b = _leaf("step_b", organism=_multi(["PvP01"]))
    old = _ast(_combine("step_c", a, b, op=CombineOp.UNION))
    new = _ast(_combine("step_c", b, a, op=CombineOp.UNION))
    wdk_ids = {"step_a": 1, "step_b": 2, "step_c": 3}

    plan = plan_step_pushes(old_ast=old, new_ast=new, existing_wdk_ids=wdk_ids)

    by_id = {p.step_id: p for p in plan}
    assert by_id["step_c"].action == RecreateAction()
    assert by_id["step_c"].reason == "combine input topology changed"
    assert by_id["step_a"].action == SkipAction()
    assert by_id["step_b"].action == SkipAction()


def test_step_kind_transition_recreates() -> None:
    leaf = _leaf("step_a")
    old_root = _transform("step_t", leaf, foo=_string("1"))
    new_root = StrategyStepNode(
        search_name="GenesByOrtholog",
        parameters={"foo": _string("1")},
        id="step_t",
    )
    wdk_ids = {"step_a": 1, "step_t": 2}

    plan = plan_step_pushes(
        old_ast=_ast(old_root), new_ast=_ast(new_root), existing_wdk_ids=wdk_ids
    )

    by_id = {p.step_id: p for p in plan}
    assert by_id["step_t"].action == RecreateAction()
    assert "step kind changed" in by_id["step_t"].reason


def test_added_step_creates_only_that_step() -> None:
    a = _leaf("step_a")
    b = _leaf("step_b")
    old = _ast(_combine("step_c", a, b, op=CombineOp.UNION))
    d = _leaf("step_d", organism=_multi(["Pk"]))
    inner = _combine("step_c", a, b, op=CombineOp.UNION)
    new = _ast(_combine("step_outer", inner, d, op=CombineOp.INTERSECT))
    wdk_ids = {"step_a": 1, "step_b": 2, "step_c": 3}

    plan = plan_step_pushes(old_ast=old, new_ast=new, existing_wdk_ids=wdk_ids)

    by_id = {p.step_id: p for p in plan}
    assert by_id["step_a"].action == SkipAction()
    assert by_id["step_b"].action == SkipAction()
    assert by_id["step_c"].action == SkipAction()
    assert by_id["step_d"].action == CreateAction()
    assert by_id["step_d"].reason == "no wdk id"
    # Outer combine is brand-new (no wdk id) → CREATE
    assert by_id["step_outer"].action == CreateAction()


def test_display_name_only_change_patches_leaf() -> None:
    old = _ast(
        StrategyStepNode(
            search_name="GenesByTaxon",
            parameters={"organism": _multi(["Pf3D7"])},
            display_name="Falciparum",
            id="step_a",
        )
    )
    new = _ast(
        StrategyStepNode(
            search_name="GenesByTaxon",
            parameters={"organism": _multi(["Pf3D7"])},
            display_name="P. falciparum genes",
            id="step_a",
        )
    )
    wdk_ids = {"step_a": 1}

    plan = plan_step_pushes(old_ast=old, new_ast=new, existing_wdk_ids=wdk_ids)

    assert plan == [
        StepPushPlan(
            step_id="step_a", action=PatchAction(), reason="display name changed"
        ),
    ]


def test_search_name_change_patches_leaf() -> None:
    old = _ast(_leaf("step_a", "GenesByTaxon", organism=_multi(["Pf3D7"])))
    new = _ast(_leaf("step_a", "GenesByOrtholog", organism=_multi(["Pf3D7"])))
    wdk_ids = {"step_a": 1}

    plan = plan_step_pushes(old_ast=old, new_ast=new, existing_wdk_ids=wdk_ids)

    assert plan == [
        StepPushPlan(step_id="step_a", action=PatchAction(), reason="search changed"),
    ]


def test_combine_metadata_only_change_patches_combine() -> None:
    a = _leaf("step_a")
    b = _leaf("step_b")
    old = _ast(_combine("step_c", a, b, op=CombineOp.UNION, display_name="A or B"))
    new = _ast(_combine("step_c", a, b, op=CombineOp.UNION, display_name="A union B"))
    wdk_ids = {"step_a": 1, "step_b": 2, "step_c": 3}

    plan = plan_step_pushes(old_ast=old, new_ast=new, existing_wdk_ids=wdk_ids)

    by_id = {p.step_id: p for p in plan}
    assert by_id["step_c"].action == PatchAction()
    assert by_id["step_c"].reason == "combine metadata changed"
    assert by_id["step_a"].action == SkipAction()
    assert by_id["step_b"].action == SkipAction()


def test_topology_changed_returns_true_when_step_added() -> None:
    a = _leaf("step_a")
    b = _leaf("step_b")
    old = _ast(_combine("step_c", a, b, op=CombineOp.UNION))
    d = _leaf("step_d")
    new = _ast(
        _combine(
            "step_outer",
            _combine("step_c", a, b, op=CombineOp.UNION),
            d,
            op=CombineOp.INTERSECT,
        )
    )

    assert topology_changed(old, new) is True


def test_topology_changed_returns_true_when_step_removed() -> None:
    a = _leaf("step_a")
    b = _leaf("step_b")
    c = _leaf("step_c")
    old = _ast(
        _combine(
            "step_outer",
            _combine("step_inner", a, b, op=CombineOp.UNION),
            c,
            op=CombineOp.INTERSECT,
        )
    )
    new = _ast(_combine("step_inner", a, b, op=CombineOp.UNION))

    assert topology_changed(old, new) is True


def test_topology_changed_returns_true_when_input_swapped() -> None:
    a = _leaf("step_a")
    b = _leaf("step_b")
    old = _ast(_combine("step_c", a, b, op=CombineOp.UNION))
    new = _ast(_combine("step_c", b, a, op=CombineOp.UNION))

    assert topology_changed(old, new) is True


def test_topology_changed_returns_false_when_only_params_changed() -> None:
    a = _leaf("step_a", organism=_multi(["Pf3D7"]))
    b = _leaf("step_b", organism=_multi(["PvP01"]))
    old = _ast(_combine("step_c", a, b, op=CombineOp.UNION))
    a2 = _leaf("step_a", organism=_multi(["Pf3D7", "Pf7G8"]))
    new = _ast(_combine("step_c", a2, b, op=CombineOp.INTERSECT))

    assert topology_changed(old, new) is False


def test_topology_changed_returns_true_when_old_ast_is_none() -> None:
    new = _ast(_leaf("step_a"))

    assert topology_changed(None, new) is True
