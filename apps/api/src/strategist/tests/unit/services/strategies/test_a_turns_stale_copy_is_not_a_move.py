from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb.wdk import turn_reads

from strategist.domain.strategy.operations import (
    ReplaceStrategyOp,
    UpdateStepParamsOp,
    UpdateStrategyMetaOp,
)
from strategist.services.strategies.commit import apply_operations_and_commit
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.live_counts import read_wdk_step_counts
from strategist.services.strategies.spec_build import build_strategy_from_spec
from strategist.services.strategies.sync_state import ensure_sync_state
from strategist.tests._support.holding_wdk import HoldingWDK
from strategist.tests.unit.services.strategies.test_a_build_turn_reads_once import (
    _SITE,
    _leaf,
    _thread,
    wdk,
)

__all__ = ["wdk"]


async def _built(wdk: HoldingWDK) -> tuple[StrategyMutationContext, int]:
    deps = _thread()
    await build_strategy_from_spec(deps=deps, root=_leaf())
    sync = ensure_sync_state(deps.strategy_session)
    await read_wdk_step_counts(sync, _SITE)
    return deps, sync.wdk_step_ids["step_a"]


def _held(wdk: HoldingWDK, step: int, name: str) -> str:
    value: str = wdk.steps[step]["searchConfig"]["parameters"][name]
    return value


def _puts(wdk: HoldingWDK, step: int, since: int) -> list[dict[str, str]]:
    return [
        w.body["parameters"]
        for w in wdk.writes[since:]
        if w.path.endswith(f"/steps/{step}/search-config")
    ]


async def test_a_build_restating_the_old_tree_after_a_fold_writes_nothing(
    wdk: HoldingWDK,
) -> None:
    with turn_reads():
        deps, step = await _built(wdk)
        wdk.steps[step]["searchConfig"]["parameters"]["text_expression"] = "rhoptry"
        await apply_operations_and_commit(
            deps=deps, ops=[UpdateStrategyMetaOp(name="Kinases")]
        )
        since = len(wdk.writes)
        await build_strategy_from_spec(deps=deps, root=_leaf())

    assert _puts(wdk, step, since) == []
    assert _held(wdk, step, "text_expression") == "rhoptry"


async def test_an_explicit_set_back_after_a_fold_is_sent(wdk: HoldingWDK) -> None:
    with turn_reads():
        deps, step = await _built(wdk)
        wdk.steps[step]["searchConfig"]["parameters"]["text_expression"] = "rhoptry"
        await apply_operations_and_commit(
            deps=deps, ops=[UpdateStrategyMetaOp(name="Kinases")]
        )
        since = len(wdk.writes)
        await apply_operations_and_commit(
            deps=deps,
            ops=[
                UpdateStepParamsOp(
                    step_id="step_a",
                    parameters={"text_expression": StringValue(value="kinase")},
                )
            ],
        )

    assert [p["text_expression"] for p in _puts(wdk, step, since)] == ["kinase"]
    assert _held(wdk, step, "text_expression") == "kinase"


async def test_an_unchanged_rebuild_writes_no_step(wdk: HoldingWDK) -> None:
    with turn_reads():
        deps, step = await _built(wdk)
        since = len(wdk.writes)
        await build_strategy_from_spec(deps=deps, root=_leaf())

    assert _puts(wdk, step, since) == []


async def test_a_website_document_type_survives_a_rebuild(wdk: HoldingWDK) -> None:
    with turn_reads():
        deps, step = await _built(wdk)
        wdk.steps[step]["searchConfig"]["parameters"]["document_type"] = "pseudogene"
        since = len(wdk.writes)
        await build_strategy_from_spec(deps=deps, root=_leaf())

    assert _puts(wdk, step, since) == []
    assert _held(wdk, step, "document_type") == "pseudogene"


async def test_a_replace_restating_the_old_tree_after_a_fold_writes_nothing(
    wdk: HoldingWDK,
) -> None:
    with turn_reads():
        deps, step = await _built(wdk)
        wdk.steps[step]["searchConfig"]["parameters"]["text_expression"] = "rhoptry"
        await apply_operations_and_commit(
            deps=deps, ops=[UpdateStrategyMetaOp(name="Kinases")]
        )
        since = len(wdk.writes)
        await apply_operations_and_commit(
            deps=deps, ops=[ReplaceStrategyOp(root=_leaf())]
        )

    assert _puts(wdk, step, since) == []
    assert _held(wdk, step, "text_expression") == "rhoptry"


async def test_a_website_document_type_rides_an_edit_of_another_value(
    wdk: HoldingWDK,
) -> None:
    with turn_reads():
        deps, step = await _built(wdk)
        wdk.steps[step]["searchConfig"]["parameters"]["document_type"] = "pseudogene"
        since = len(wdk.writes)
        await apply_operations_and_commit(
            deps=deps,
            ops=[
                UpdateStepParamsOp(
                    step_id="step_a",
                    parameters={"text_expression": StringValue(value="protease")},
                )
            ],
        )

    assert [
        (p["text_expression"], p["document_type"]) for p in _puts(wdk, step, since)
    ] == [("protease", "pseudogene")]
