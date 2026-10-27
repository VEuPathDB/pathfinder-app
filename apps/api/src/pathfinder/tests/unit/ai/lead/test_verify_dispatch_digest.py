"""A verification verdict is computed from the build and the checks on the
site. The checker's digest carries its notes and never moves the verdict."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pytest
from veupathdb.domain.strategy import StepKind, StrategyStep

from pathfinder.ai.graph.state import FailureCause, PhaseDisposition
from pathfinder.ai.lead import sub_agent_tools
from pathfinder.ai.lead.answered_strategy import live_tree
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.caveats import BuildCaveat
from pathfinder.domain.site_checks import SiteCheck, SiteCheckGap
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.site_checks import PASSED, checked_site
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.ai.lead.conftest import (
    final_result_model,
    lead_deps,
    pipeline_state,
)

_COMBINATION = "mass spectrometry evidence OR DeRisi expression"

_BUILD_DIGEST: dict[str, Any] = {
    "digest": {
        "prose": (
            "The sampled records are protein kinases of Cryptosporidium parvum Iowa II."
        ),
    },
}
_OBJECTING_DIGEST: dict[str, Any] = {
    "digest": {
        "handoffTo": "frame",
        "prose": "No step computes or ranks the counts by organism.",
    },
}
_COMBINE = SiteCheck(
    kind="combine_counts",
    subject="the strategy on the site",
    status="fail",
    evidence=(
        "a count its operator cannot hold: INTERSECT 'Both' holds 90 from "
        "inputs of 61 and 400"
    ),
)

pytestmark = pytest.mark.usefixtures("collector")


def _session_with_step(
    site_id: str,
    *,
    name: str,
    search_name: str,
    count: int,
    wdk_strategy_id: int,
) -> StrategySession:
    session = StrategySession(site_id=site_id)
    graph = StrategyGraph("graph-1", name, site_id)
    graph.record_type = "transcript"
    add_step_to_graph(
        graph,
        StrategyStep(id="s1", kind=StepKind.SEARCH, search_name=search_name),
    )
    session.add_graph(graph)
    session.sync_state = WDKSyncState(
        wdk_step_ids={"s1": 440186113},
        step_counts={"s1": count},
        wdk_strategy_id=wdk_strategy_id,
    )
    return session


async def _verify(
    monkeypatch: pytest.MonkeyPatch,
    deps: LeadDeps,
    digest: dict[str, Any],
    checks: Sequence[SiteCheck] = (PASSED,),
) -> VerificationDelta:
    checked_site(monkeypatch, checks)
    monkeypatch.setattr(
        sub_agent_tools,
        "get_mock_model",
        lambda: final_result_model(digest),
    )
    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions="Return the digest the script names.",
    ):
        result = await run_verification(
            deps=deps,
            parent_tool_call_id="lead_call_verify",
            reason="check the strategy",
        )
    assert isinstance(result, VerificationDelta)
    return result


def _kinase_deps(session: StrategySession) -> LeadDeps:
    state = pipeline_state(
        "cryptodb",
        user_prompt="Build me a strategy for Cryptosporidium kinases.",
    )
    return lead_deps(state, strategy_session=session)


async def test_a_zero_push_build_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _kinase_deps(StrategySession(site_id="cryptodb"))

    delta = await _verify(monkeypatch, deps, _BUILD_DIGEST)

    assert delta.digest.success is False
    assert delta.digest.reason == (
        "The build pushed 0 steps, failed 0, skipped 0 and left 0 empty"
    )
    assert delta.digest.caveats == [BuildCaveat(pushed=0, failed=0, skipped=0, empty=0)]
    recorded = deps.state.domain.site_verdict
    assert recorded is not None
    assert recorded.success is False


async def test_a_real_build_whose_checks_pass_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _kinase_deps(
        _session_with_step(
            "cryptodb",
            name="Kinases",
            search_name="GenesByText",
            count=61,
            wdk_strategy_id=330558093,
        ),
    )
    deps.state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"],
        wdk_strategy_id=330558093,
    )

    delta = await _verify(monkeypatch, deps, _BUILD_DIGEST)

    assert delta.digest.success is True
    assert delta.digest.disposition is PhaseDisposition.DONE
    assert delta.digest.reason == "No check of the strategy on the site failed"
    assert delta.digest.review.checks == [PASSED]
    assert delta.digest.caveats == []


async def test_the_verdict_stands_for_the_revision_it_judged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _session_with_step(
        "cryptodb",
        name="Kinases",
        search_name="GenesByText",
        count=61,
        wdk_strategy_id=330558093,
    )
    deps = _kinase_deps(session)
    deps.state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"], wdk_strategy_id=330558093
    )
    judged = live_tree(session.get_graph(None))
    deps.state.domain.answered_graph = judged

    delta = await _verify(monkeypatch, deps, _BUILD_DIGEST)

    assert deps.state.domain.verified_revision == strategy_revision(judged)
    assert len(deps.state.domain.verified_revision) == 16
    assert deps.state.turn_verdict == delta.digest


def _built_kinases() -> LeadDeps:
    deps = _kinase_deps(
        _session_with_step(
            "cryptodb",
            name="Kinases",
            search_name="GenesByText",
            count=61,
            wdk_strategy_id=330558093,
        ),
    )
    deps.state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"], wdk_strategy_id=330558093
    )
    return deps


async def test_an_objecting_checker_never_fails_a_passing_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _built_kinases()

    delta = await _verify(monkeypatch, deps, _OBJECTING_DIGEST)

    digest = delta.digest
    assert (digest.success, digest.gaps, digest.handoff_to) == (True, [], None)
    assert digest.prose == "No step computes or ranks the counts by organism."
    assert deps.state.turn_markers.verified is True


async def test_a_failed_check_fails_the_verdict_with_the_sites_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _built_kinases()

    delta = await _verify(monkeypatch, deps, _BUILD_DIGEST, [PASSED, _COMBINE])

    digest = delta.digest
    assert (digest.success, digest.failure_cause) == (
        False,
        FailureCause.STRUCTURE_VIOLATION,
    )
    assert digest.gaps == [SiteCheckGap(check=_COMBINE)]
    assert digest.reason == (
        "'the strategy on the site': a count its operator cannot hold: INTERSECT "
        "'Both' holds 90 from inputs of 61 and 400"
    )
    assert digest.disposition is PhaseDisposition.HANDOFF
    assert deps.state.turn_markers.verified is False


async def test_an_unchecked_requirement_never_fails_the_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unchecked = SiteCheck(
        kind=ConstraintKind.OTHER,
        subject="which organisms have the most singletons",
        status="unchecked",
        evidence="no check reads this requirement on the site",
        why_unchecked="no_check",
        requirement="other:which organisms have the most singletons",
    )

    delta = await _verify(
        monkeypatch, _built_kinases(), _OBJECTING_DIGEST, [PASSED, unchecked]
    )

    assert (delta.digest.success, delta.digest.gaps) == (True, [])
    assert delta.digest.review.checks == [PASSED, unchecked]
