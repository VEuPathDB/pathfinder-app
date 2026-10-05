"""A sweep names a step the strategy holds on the site, and its schema reads the
same whatever the strategy holds."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import StrategyStepNode

from pathfinder.ai.lead.lead_agent import build_sweep_toolset
from pathfinder.ai.tools.standalone.optimization import sweep_can_run
from pathfinder.domain.evidence import NamedControlSet
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import session_with

_SAVED_SET_ID = "96eaafb0-659c-4041-8bf3-5c66e5a9f95c"


def _built() -> StrategyStepNode:
    return StrategyStepNode(id="step_sp", search_name="GenesWithSignalPeptide")


async def test_a_step_the_strategy_does_not_hold_is_refused_before_the_card() -> None:
    ctx = lead_run_context(
        strategy_session=session_with(_built(), {"step_sp": 440649693})
    )
    ctx.deps.state.domain.attach_control_set(
        NamedControlSet(id=_SAVED_SET_ID, name="Signal peptide controls")
    )

    with pytest.raises(ModelRetry) as raised:
        await sweep_can_run(
            ctx,
            wdk_step_id=440606243,
            control_set_id=_SAVED_SET_ID,
            reply="I will sweep the SignalP version against your controls.",
        )

    assert str(raised.value) == (
        "Step 440606243 is no step of this strategy on the site. Its steps are "
        "440649693. Nothing was started and no card was shown."
    )


async def test_the_sweep_schema_is_the_same_before_and_after_a_build() -> None:
    toolset = build_sweep_toolset()
    empty = lead_run_context()
    built = lead_run_context(
        strategy_session=session_with(_built(), {"step_sp": 440649693})
    )

    before = await toolset.get_tools(empty)
    after = await toolset.get_tools(built)

    assert [t.tool_def for t in before.values()] == [t.tool_def for t in after.values()]
