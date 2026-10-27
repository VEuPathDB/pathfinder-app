from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    PHYLETIC_EXPRESSION_SEARCH,
    StringValue,
)
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKStepTree, WDKStrategyDetails

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import evidence_card, verify_checks, verify_dispatch
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.ai.tools.standalone._result_models import StepColumns
from pathfinder.domain.expression_fit import ExpressionFit
from pathfinder.domain.site_checks import SiteCheck, SiteCheckGap
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.services.strategies.site_counts import SiteCounts
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests.unit.ai.lead.conftest import (
    ChunkCollector,
    lead_deps,
    pipeline_state,
)

_ROOT = 227284080
_STRATEGY = 214644930
_ASKED = "Groups with exactly one protein in every apicomplexan genome"
_FAILING = ExpressionFit(
    wdk_step_id=_ROOT,
    expression="APIC=139T AND APIC=139",
    sampled=2,
    held=1,
    failing=["OG8_0031041"],
)
_UNMATCHED_EXPRESSION = "APIC>=1T AND MAMM<=0T"
_ZERO_BOUND = (
    "MAMM<=0T matches no group, because the site counts a unit only in a group "
    "with a protein of its codes; write MAMM=0T for absence."
)

pytestmark = pytest.mark.usefixtures("collector")


def _gap(fit: ExpressionFit) -> SiteCheckGap:
    return SiteCheckGap(
        check=SiteCheck(
            kind="expression_fit",
            subject=f"phyletic expression {fit.expression}",
            status="fail",
            evidence=fit.sentence,
        )
    )


def _spec(expression: str) -> OperationalSpec:
    value = StringValue(value=expression)
    return OperationalSpec(
        goal=_ASKED,
        criteria=[
            Criterion(
                id="c1",
                text=_ASKED,
                search_name=PHYLETIC_EXPRESSION_SEARCH,
                resolved_params=bind_values(
                    {PHYLETIC_EXPRESSION_PARAM: value}, "stated", []
                ),
            )
        ],
    )


def _deps(count: int, expression: str) -> LeadDeps:
    state = pipeline_state("orthomcl", user_prompt=_ASKED)
    state.domain.original_request = _ASKED
    state.domain.request_messages = [_ASKED]
    state.domain.operational_spec = _spec(expression)
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["c1"],
        wdk_strategy_id=_STRATEGY,
        node_results=[
            NodeResult(
                node_id="c1",
                search_name=PHYLETIC_EXPRESSION_SEARCH,
                wdk_step_id=_ROOT,
                status="ok",
            )
        ],
    )
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph(graph_id="g1", name="Single copy", site_id="orthomcl")
    graph.record_type = "group"
    graph.steps = flatten_tree(
        StrategyStepNode(id="c1", search_name=PHYLETIC_EXPRESSION_SEARCH)
    )
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={"c1": _ROOT},
        step_counts={"c1": count},
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree(step_id=_ROOT),
    )
    return lead_deps(state, strategy_session=session)


async def _run(
    monkeypatch: pytest.MonkeyPatch, deps: LeadDeps, count: int
) -> VerificationDelta:
    outcome = VerificationDelta.model_validate(
        {"digest": {"prose": "The strategy answers the request.", "review": {}}}
    )

    async def streamed(**kwargs: Any) -> VerificationDelta:
        del kwargs
        return outcome

    async def counts(site_id: str, wdk_strategy_id: int) -> SiteCounts:
        del site_id, wdk_strategy_id
        return SiteCounts(root_step_id=_ROOT, counts={_ROOT: count})

    async def held_columns(deps: AgentDeps, wdk_step_id: int) -> StepColumns:
        del deps
        return StepColumns(wdk_step_id=wdk_step_id)

    async def held(site_id: str, wdk_strategy_id: int) -> WDKStrategyDetails:
        del site_id
        return WDKStrategyDetails.model_validate(
            {
                "strategyId": wdk_strategy_id,
                "name": "Single copy",
                "rootStepId": _ROOT,
                "stepTree": {"stepId": _ROOT},
                "steps": {
                    str(_ROOT): {
                        "id": _ROOT,
                        "searchName": PHYLETIC_EXPRESSION_SEARCH,
                        "searchConfig": {"parameters": {}},
                        "recordClassName": "group",
                        "estimatedSize": count,
                        "validation": {"level": "RUNNABLE", "isValid": True},
                    }
                },
            }
        )

    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", streamed)
    monkeypatch.setattr(evidence_card, "read_step_counts", counts)
    monkeypatch.setattr(verify_checks, "read_step_columns", held_columns)
    monkeypatch.setattr(verify_checks, "read_site_strategy", held)
    delta = await run_verification(
        deps=deps, parent_tool_call_id="call_verify", reason="check the groups"
    )
    assert isinstance(delta, VerificationDelta)
    return delta


async def test_a_failing_sampled_group_fails_the_check_and_is_on_the_card(
    monkeypatch: pytest.MonkeyPatch, collector: ChunkCollector
) -> None:
    deps = _deps(2, _FAILING.expression)
    deps.state.turn_markers.record_expression_fit(_FAILING)
    deps.state.turn_markers.record_expression_fit(
        _FAILING.model_copy(update={"wdk_step_id": _ROOT + 1})
    )

    delta = await _run(monkeypatch, deps, 2)

    assert (delta.digest.success, delta.digest.gaps, delta.digest.caveats) == (
        False,
        [_gap(_FAILING)],
        [],
    )
    assert delta.digest.gaps[0].sentence == (
        f"'phyletic expression {_FAILING.expression}': "
        f"1 of 2 sampled groups of step {_ROOT} does not meet its phyletic "
        "expression on the site's per-genome counts: OG8_0031041"
    )
    card = deps.state.domain.last_evidence_card
    assert card is not None
    assert card.expression_fits == [_FAILING]
    streamed = collector.data_of("data-evidence-card")[0]["expressionFits"]
    assert [fit["failing"] for fit in streamed] == [["OG8_0031041"]]


async def test_an_empty_step_the_site_cannot_match_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(0, _UNMATCHED_EXPRESSION)
    unmatched = ExpressionFit(
        wdk_step_id=_ROOT,
        expression=_UNMATCHED_EXPRESSION,
        sampled=0,
        held=0,
        unmatched=[_ZERO_BOUND],
    )
    deps.state.turn_markers.record_expression_fit(unmatched)

    delta = await _run(monkeypatch, deps, 0)

    empty = SiteCheck(
        kind="result_count",
        subject="the strategy on the site",
        status="fail",
        evidence=f"the result step {_ROOT} ('GroupsByPhyleticPattern') holds no "
        "record on the site",
    )
    assert (delta.digest.success, delta.digest.gaps) == (
        False,
        [SiteCheckGap(check=empty), _gap(unmatched)],
    )
    assert delta.digest.gaps[1].sentence == (
        f"'phyletic expression {_UNMATCHED_EXPRESSION}': "
        f"step {_ROOT} holds no group, and its phyletic expression matches none "
        f"as the site reads it: {_ZERO_BOUND}"
    )


async def test_a_fit_every_sampled_group_meets_is_no_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(2, _FAILING.expression)
    deps.state.turn_markers.record_expression_fit(
        _FAILING.model_copy(update={"held": 2, "failing": []})
    )

    delta = await _run(monkeypatch, deps, 2)

    assert (delta.digest.success, delta.digest.gaps, delta.digest.caveats) == (
        True,
        [],
        [],
    )


async def test_a_step_rebound_in_place_drops_the_fit_of_its_old_expression(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _deps(0, _UNMATCHED_EXPRESSION)
    deps.state.turn_markers.record_expression_fit(
        ExpressionFit(
            wdk_step_id=_ROOT,
            expression=_UNMATCHED_EXPRESSION,
            sampled=0,
            held=0,
            unmatched=[_ZERO_BOUND],
        )
    )
    first = await _run(monkeypatch, deps, 0)
    deps.state.domain.operational_spec = _spec("APIC>=1T AND MAMM=0T")

    second = await _run(monkeypatch, deps, 2)

    card = deps.state.domain.last_evidence_card
    assert card is not None
    assert (first.digest.success, second.digest.success, second.digest.gaps) == (
        False,
        True,
        [],
    )
    assert card.expression_fits == []
