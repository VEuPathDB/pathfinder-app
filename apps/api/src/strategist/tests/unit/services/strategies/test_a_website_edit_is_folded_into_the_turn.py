from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.wdk import turn_reads

from strategist.ai.lead.verify_checks import _bound_values, _judged
from strategist.domain.strategy.operations import (
    ReplaceStrategyOp,
    UpdateStepParamsOp,
    UpdateStrategyMetaOp,
)
from strategist.domain.strategy.operations.types import GraphOperation
from strategist.services.strategies.commit import (
    CommitResult,
    apply_operations_and_commit,
)
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.live_counts import read_wdk_step_counts
from strategist.services.strategies.site_counts import read_site_strategy
from strategist.services.strategies.sync_state import ensure_sync_state
from strategist.tests._support.holding_wdk import HoldingWDK
from strategist.tests.unit.services.strategies.test_a_build_turn_reads_once import (
    _SITE,
    _leaf,
    _thread,
    wdk,
)

__all__ = ["wdk"]


async def _a_turn(
    wdk: HoldingWDK, website: dict[str, object], *edits: GraphOperation
) -> tuple[StrategyMutationContext, int, list[CommitResult]]:
    deps = _thread()
    with turn_reads():
        await apply_operations_and_commit(
            deps=deps, ops=[ReplaceStrategyOp(root=_leaf())]
        )
        sync = ensure_sync_state(deps.strategy_session)
        step = sync.wdk_step_ids["step_a"]
        await read_wdk_step_counts(sync, _SITE)
        config = wdk.steps[step]["searchConfig"]
        for name, value in website.items():
            if name == "wdkWeight":
                config["wdkWeight"] = value
            else:
                config["parameters"][name] = value
        results: list[CommitResult] = [
            await apply_operations_and_commit(deps=deps, ops=[edit]) for edit in edits
        ]
    return deps, step, results


def _rename(name: str) -> UpdateStrategyMetaOp:
    return UpdateStrategyMetaOp(name=name)


async def test_a_website_weight_stays_through_two_renames(wdk: HoldingWDK) -> None:
    deps, step, results = await _a_turn(
        wdk,
        {"wdkWeight": 10, "text_expression": "rhoptry"},
        _rename("Kinases"),
        _rename("Kinases in P. berghei"),
    )

    graph = deps.strategy_session.graph
    assert graph is not None
    assert [r.failures for r in results] == [[], []]
    assert wdk.written("PUT", f"/steps/{step}/search-config") == []
    held = wdk.steps[step]["searchConfig"]
    assert (held["wdkWeight"], held["parameters"]["text_expression"]) == (
        10,
        "rhoptry",
    )
    assert graph.steps["step_a"].wdk_weight == 10
    assert ensure_sync_state(deps.strategy_session).wdk_push_errors == {}


async def test_a_website_value_is_the_turns_after_the_next_commit(
    wdk: HoldingWDK,
) -> None:
    deps, _step, results = await _a_turn(
        wdk, {"text_expression": "rhoptry"}, _rename("Kinases")
    )

    graph = deps.strategy_session.graph
    assert graph is not None
    sync = ensure_sync_state(deps.strategy_session)
    assert results[0].failures == []
    assert graph.steps["step_a"].parameters["text_expression"] == StringValue(
        value="rhoptry"
    )
    details = await read_site_strategy(_SITE, sync.wdk_strategy_id or 0)
    assert details is not None
    check = await _bound_values(_judged(_SITE, graph, sync, details))
    assert check.status == "pass"


async def test_after_a_failed_read_the_next_edit_keeps_another_website_value(
    wdk: HoldingWDK,
) -> None:
    deps = _thread()
    with turn_reads():
        await apply_operations_and_commit(
            deps=deps, ops=[ReplaceStrategyOp(root=_leaf())]
        )
        sync = ensure_sync_state(deps.strategy_session)
        step = sync.wdk_step_ids["step_a"]
        wdk.steps[step]["searchConfig"]["parameters"]["text_expression"] = "rhoptry"
        wdk.refuses_once.add("strategy read")
        organism = UpdateStepParamsOp(
            step_id="step_a",
            parameters={
                "text_search_organism": MultiPickValue(
                    values=["Plasmodium falciparum 3D7"]
                )
            },
        )
        failed = await apply_operations_and_commit(deps=deps, ops=[organism])
        await apply_operations_and_commit(deps=deps, ops=[organism])

    assert len(failed.failures) == 1
    held = wdk.steps[step]["searchConfig"]["parameters"]
    assert (held["text_expression"], held["text_search_organism"]) == (
        "rhoptry",
        '["Plasmodium falciparum 3D7"]',
    )
