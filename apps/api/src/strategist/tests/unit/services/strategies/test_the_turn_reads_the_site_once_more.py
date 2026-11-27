from __future__ import annotations

from veupathdb.domain.parameters import HeldValue, StringValue
from veupathdb.wdk import turn_reads

from strategist.ai.graph.state import PipelineState
from strategist.ai.lead.answered_strategy import (
    take_the_sites_fold,
    the_strategy_now_answers_to,
)
from strategist.ai.lead.lead_pins import pinned_spec_as_the_site_holds_it
from strategist.ai.lead.pre_turn import stated_spec_of
from strategist.domain.strategy.operational_spec import OperationalSpec
from strategist.domain.strategy.operations import (
    UpdateStepParamsOp,
    UpdateStrategyMetaOp,
)
from strategist.services.strategies.commit import apply_operations_and_commit
from strategist.services.strategies.context import StrategyMutationContext
from strategist.services.strategies.spec_build import build_strategy_from_spec
from strategist.services.strategies.sync_state import ensure_sync_state
from strategist.tests._support.holding_wdk import HoldingWDK
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from strategist.tests.unit.services.strategies.test_a_build_turn_reads_once import (
    _SITE,
    _leaf,
)
from strategist.tests.unit.services.strategies.test_a_turns_stale_copy_is_not_a_move import (
    _built,
    _held,
    _puts,
    wdk,
)

__all__ = ["wdk"]


async def _framed(
    deps: StrategyMutationContext,
) -> tuple[PipelineState, OperationalSpec]:
    graph = deps.strategy_session.graph
    assert graph is not None
    ast = graph.to_strategy_ast()
    assert ast is not None
    spec = await stated_spec_of(ast, site_id=_SITE, goal="kinases")
    state = pipeline_state(user_prompt="kinases")
    state.domain.operational_spec = spec
    the_strategy_now_answers_to(state, spec, graph)
    return state, spec


def _stated(state: PipelineState) -> object:
    spec = state.domain.operational_spec
    assert spec is not None
    return spec.criteria[0].resolved_params["text_expression"].value


async def _folded(
    wdk: HoldingWDK,
) -> tuple[StrategyMutationContext, int, PipelineState]:
    deps, step = await _built(wdk)
    state, _ = await _framed(deps)
    wdk.steps[step]["searchConfig"]["parameters"]["text_expression"] = "rhoptry"
    await apply_operations_and_commit(
        deps=deps, ops=[UpdateStrategyMetaOp(name="Kinases")]
    )
    return deps, step, state


async def test_a_value_the_turn_set_after_the_fold_is_not_an_outside_change(
    wdk: HoldingWDK,
) -> None:
    with turn_reads():
        deps, _step, state = await _folded(wdk)
        before = _stated(state)
        await apply_operations_and_commit(
            deps=deps,
            ops=[
                UpdateStepParamsOp(
                    step_id="step_a",
                    parameters={"text_expression": StringValue(value="protease")},
                )
            ],
        )
        changes = await take_the_sites_fold(state, deps.strategy_session, site_id=_SITE)

    assert changes.moved is False
    assert _stated(state) == before


async def test_a_stored_default_the_site_holds_otherwise_is_not_written(
    wdk: HoldingWDK,
) -> None:
    with turn_reads():
        deps, step = await _built(wdk)
        graph = deps.strategy_session.graph
        assert graph is not None
        graph.steps["step_a"].parameters["document_type"] = StringValue(value="gene")
        wdk.steps[step]["searchConfig"]["parameters"]["document_type"] = "pseudogene"
        since = len(wdk.writes)
        await build_strategy_from_spec(deps=deps, root=_leaf())

    assert _puts(wdk, step, since) == []
    assert _held(wdk, step, "document_type") == "pseudogene"


async def test_a_step_whose_write_was_refused_keeps_the_sites_values(
    wdk: HoldingWDK,
) -> None:
    protease = UpdateStepParamsOp(
        step_id="step_a",
        parameters={"text_expression": StringValue(value="protease")},
    )
    with turn_reads():
        deps, step = await _built(wdk)
        wdk.refuses_once.add("search-config put")
        await apply_operations_and_commit(deps=deps, ops=[protease])
        assert "step_a" in ensure_sync_state(deps.strategy_session).wdk_push_errors
        wdk.steps[step]["searchConfig"]["parameters"]["document_type"] = "pseudogene"
        since = len(wdk.writes)
        await apply_operations_and_commit(
            deps=deps, ops=[UpdateStrategyMetaOp(name="Kinases")]
        )

    assert [
        (p["text_expression"], p["document_type"]) for p in _puts(wdk, step, since)
    ] == [("protease", "pseudogene")]


async def test_the_leads_spec_shows_the_sites_value_after_a_fold(
    wdk: HoldingWDK,
) -> None:
    with turn_reads():
        deps, _step, state = await _folded(wdk)
        ctx = run_context_for(lead_deps(state, strategy_session=deps.strategy_session))
        stale = _stated(state)
        await pinned_spec_as_the_site_holds_it(ctx)

    assert stale != HeldValue(wire="rhoptry")
    assert _stated(state) == HeldValue(wire="rhoptry")
