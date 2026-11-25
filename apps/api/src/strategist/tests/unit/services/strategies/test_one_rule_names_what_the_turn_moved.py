from __future__ import annotations

import pytest
from veupathdb.domain.parameters import HeldValue, NumberValue, ParamValue, StringValue
from veupathdb.domain.strategy import StepKind, StepSettings, StrategyStep

from strategist.services.strategies.commit_read import the_turns_own
from strategist.services.strategies.step_push_planner import (
    TurnBaseline,
    moved_by_the_turn,
)


@pytest.mark.parametrize(
    ("plan", "started", "site"),
    [
        (StringValue(value="kinase"), HeldValue(wire="kinase"), "rhoptry"),
        (HeldValue(wire="kinase"), StringValue(value="kinase"), "rhoptry"),
        (NumberValue(value=10), HeldValue(wire="10.0"), "12"),
    ],
)
def test_a_value_the_turn_holds_in_another_form_is_not_the_turns(
    plan: ParamValue, started: ParamValue, site: str
) -> None:
    step = StrategyStep(
        id="step_a",
        kind=StepKind.SEARCH,
        search_name="GenesByText",
        parameters={"text_expression": plan},
    )
    was = StepSettings(
        search_name="GenesByText", parameters={"text_expression": started}
    )
    held = StepSettings(
        search_name="GenesByText",
        parameters={"text_expression": HeldValue(wire=site)},
    )
    stated = StepSettings(search_name="GenesByText", parameters=step.parameters)

    base = TurnBaseline(started=was)
    own = the_turns_own({"step_a": step}, {"step_a": base})

    assert own.holds("step_a", "text_expression") is False
    assert moved_by_the_turn(stated, held, base) == []
