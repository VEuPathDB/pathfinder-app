from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from strategist.services.strategies.step_push_planner import (
    SkipAction,
    plan_step_pushes,
)
from strategist.tests._support.wdk_write_stubs import held_as

_ORGANISMS = ["Plasmodium falciparum 3D7", "Plasmodium vivax P01"]


def _signal(terms: list[str]) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="signal",
            search_name="GenesWithSignalPeptide",
            parameters={"organism": MultiPickValue(values=terms)},
        ),
    )


def test_a_step_whose_picks_change_only_their_order_is_skipped() -> None:
    plan = plan_step_pushes(
        old_ast=_signal(_ORGANISMS),
        new_ast=_signal(_ORGANISMS[::-1]),
        existing_wdk_ids={"signal": 100},
        held=held_as(_signal(_ORGANISMS)),
        unfinished=frozenset(),
    )

    assert [entry.action for entry in plan] == [SkipAction()]
