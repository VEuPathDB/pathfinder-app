"""A newly added step with unfilled required params is a DRAFT, not an error.

Every graph operation commits to WDK, and push-time validation used to raise
``ValidationError`` when any step lacked a required parameter. The UI adds a
step first and collects parameters afterwards (the ortholog sheet literally
says "You can edit parameters after insertion", and the editor opens on the
new step), so that hard failure surfaced as a 422 on the very first click for
any search with a required parameter.

A step that has never reached WDK is allowed to sit incomplete. A step that
IS already in WDK must not silently regress into a draft: rewriting it with
missing params is a real error the user has to see.
"""

from veupathdb.domain.strategy import StepKind, StrategyStep

from pathfinder.services.strategies.step_push_planner import (
    CreateAction,
    PatchAction,
    SkipAction,
    StepPushPlan,
)
from pathfinder.services.strategies.step_wdk_push import defer_draft_steps


def _step(step_id: str) -> StrategyStep:
    return StrategyStep(
        id=step_id, kind=StepKind.SEARCH, search_name="GenesByOrthologPattern"
    )


def _steps(*ids: str) -> dict[str, StrategyStep]:
    return {step_id: _step(step_id) for step_id in ids}


def _ids(plan: list[StepPushPlan]) -> list[str]:
    return [entry.step_id for entry in plan]


def _plan(
    step_id: str, action: CreateAction | PatchAction | SkipAction
) -> StepPushPlan:
    return StepPushPlan(step_id=step_id, action=action, reason="test")


def test_new_step_with_missing_params_is_deferred() -> None:
    plan = [_plan("s1", CreateAction())]
    result = defer_draft_steps(
        plan,
        steps_by_id=_steps(*_ids(plan)),
        open_param_step_ids={"s1"},
        existing_wdk_ids={},
    )
    assert isinstance(result[0].action, SkipAction)
    assert "draft" in result[0].reason.lower()


def test_complete_new_step_still_pushes() -> None:
    plan = [_plan("s1", CreateAction())]
    result = defer_draft_steps(
        plan,
        steps_by_id=_steps(*_ids(plan)),
        open_param_step_ids=set(),
        existing_wdk_ids={},
    )
    assert isinstance(result[0].action, CreateAction)


def test_step_already_in_wdk_is_not_deferred() -> None:
    # Regressing a live WDK step into a draft would silently strip it from
    # the built strategy; the user must be told instead.
    plan = [_plan("s1", PatchAction())]
    result = defer_draft_steps(
        plan,
        steps_by_id=_steps(*_ids(plan)),
        open_param_step_ids={"s1"},
        existing_wdk_ids={"s1": 12345},
    )
    assert isinstance(result[0].action, PatchAction)


def test_only_the_incomplete_step_is_deferred() -> None:
    plan = [_plan("s1", CreateAction()), _plan("s2", CreateAction())]
    result = defer_draft_steps(
        plan,
        steps_by_id=_steps(*_ids(plan)),
        open_param_step_ids={"s1"},
        existing_wdk_ids={},
    )
    by_id = {p.step_id: p.action for p in result}
    assert isinstance(by_id["s1"], SkipAction)
    assert isinstance(by_id["s2"], CreateAction)


def test_plan_order_and_length_are_preserved() -> None:
    plan = [_plan("a", CreateAction()), _plan("b", CreateAction())]
    result = defer_draft_steps(
        plan,
        steps_by_id=_steps(*_ids(plan)),
        open_param_step_ids={"a"},
        existing_wdk_ids={},
    )
    assert [p.step_id for p in result] == ["a", "b"]


def test_already_skipped_steps_are_untouched() -> None:
    plan = [_plan("s1", SkipAction())]
    result = defer_draft_steps(
        plan,
        steps_by_id=_steps(*_ids(plan)),
        open_param_step_ids={"s1"},
        existing_wdk_ids={},
    )
    assert isinstance(result[0].action, SkipAction)


def test_empty_plan_is_empty() -> None:
    assert (
        defer_draft_steps(
            [], steps_by_id={}, open_param_step_ids=set(), existing_wdk_ids={}
        )
        == []
    )
