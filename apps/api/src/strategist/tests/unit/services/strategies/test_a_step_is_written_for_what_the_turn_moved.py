from veupathdb.domain.strategy import StepFilter, StrategyStepNode

from strategist.services.strategies.step_push_planner import (
    PatchAction,
    RecreateAction,
    SkipAction,
    TheTurn,
    plan_step_pushes,
)
from strategist.tests._support.wdk_write_stubs import held_as
from strategist.tests.unit.services.strategies.test_step_push_planner import (
    _ast,
    _combine,
    _leaf,
    _multi,
)


def _filtered(node: StrategyStepNode, *values: str) -> StrategyStepNode:
    return node.model_copy(
        update={
            "filters": [
                StepFilter(
                    name="matched_transcript_filter_array",
                    value={"values": list(values)},
                )
            ]
        }
    )


def test_a_filter_only_change_on_a_leaf_patches_its_search_config() -> None:
    a = _leaf("step_a")
    b = _leaf("step_b")
    old = _ast(_combine("step_c", _filtered(a, "Y"), b))
    new = _ast(_combine("step_c", _filtered(a, "N"), b))
    wdk_ids = {"step_a": 1, "step_b": 2, "step_c": 3}

    plan = plan_step_pushes(
        old_ast=old,
        new_ast=new,
        existing_wdk_ids=wdk_ids,
        held=held_as(old),
        turn=TheTurn(),
    )

    by_id = {p.step_id: p.action for p in plan}
    assert by_id == {
        "step_a": PatchAction(search_config=True, name=False),
        "step_b": SkipAction(),
        "step_c": SkipAction(),
    }


def test_a_filter_change_on_a_combine_recreates_it() -> None:
    a = _leaf("step_a")
    b = _leaf("step_b")
    old = _ast(_combine("step_c", a, b))
    new = _ast(_filtered(_combine("step_c", a, b), "YY"))
    wdk_ids = {"step_a": 1, "step_b": 2, "step_c": 3}

    plan = plan_step_pushes(
        old_ast=old,
        new_ast=new,
        existing_wdk_ids=wdk_ids,
        held=held_as(old),
        turn=TheTurn(),
    )

    assert [p.action for p in plan] == [SkipAction(), SkipAction(), RecreateAction()]


def test_a_value_restated_in_its_canonical_spelling_is_not_written() -> None:
    old = _ast(_leaf("step_a", organism=_multi(["Pf3D7", "PvP01"])))
    new = _ast(_leaf("step_a", organism=_multi(["PvP01", "Pf3D7"])))

    plan = plan_step_pushes(
        old_ast=old,
        new_ast=new,
        existing_wdk_ids={"step_a": 1},
        held=held_as(old),
        turn=TheTurn(),
    )

    assert [p.action for p in plan] == [SkipAction()]


def test_a_value_the_turn_did_not_move_is_not_written_back() -> None:
    old = _ast(_leaf("step_a", organism=_multi(["Pf3D7"])))
    site = _ast(_leaf("step_a", organism=_multi(["PvP01"])))

    plan = plan_step_pushes(
        old_ast=old,
        new_ast=old,
        existing_wdk_ids={"step_a": 1},
        held=held_as(site),
        turn=TheTurn(),
    )

    assert [p.action for p in plan] == [SkipAction()]


def test_a_step_whose_last_write_did_not_land_is_written_against_the_site() -> None:
    old = _ast(_leaf("step_a", organism=_multi(["Pf3D7"])))
    site = _ast(_leaf("step_a", organism=_multi(["PvP01"])))

    plan = plan_step_pushes(
        old_ast=old,
        new_ast=old,
        existing_wdk_ids={"step_a": 1},
        held=held_as(site),
        turn=TheTurn(unfinished=frozenset({"step_a"})),
    )

    assert [p.action for p in plan] == [PatchAction(search_config=True, name=False)]
