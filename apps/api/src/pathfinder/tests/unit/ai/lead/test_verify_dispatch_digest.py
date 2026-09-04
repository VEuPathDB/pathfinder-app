"""A verification verdict never says more than the build or the structure holds.

A success over a build that pushed nothing, or over a tree that answers another
question, is rewritten to the failure the ledger holds.
"""

from __future__ import annotations

from typing import Any

import pytest

from pathfinder.ai.graph.state import FailureCause, PhaseDisposition
from pathfinder.ai.lead import sub_agent_tools
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.graph_model import StepKind, StrategyStep
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.ops import CombineOp
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.ai.lead.conftest import (
    final_result_model,
    lead_deps,
    pipeline_state,
    requirement,
)

_COMBINATION = "mass spectrometry evidence OR DeRisi expression"

_BUILD_DIGEST: dict[str, Any] = {
    "digest": {
        "disposition": "done",
        "prose": (
            "**Verified end-to-end.** The strategy framed, built, and verified "
            "cleanly - root size looks right and the leaves are non-empty."
        ),
        "reason": "Verified successfully",
        "success": True,
    },
}
_STRUCTURE_DIGEST: dict[str, Any] = {
    "digest": {
        "disposition": "done",
        "prose": (
            "**Verified end-to-end.** The empty result is explained by the "
            "downstream combination; relaxing the peptide threshold would fill it."
        ),
        "reason": "Verified successfully",
        "success": True,
    },
}

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
) -> VerificationDelta:
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


async def test_success_over_a_zero_push_build_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _kinase_deps(StrategySession(site_id="cryptodb"))

    delta = await _verify(monkeypatch, deps, _BUILD_DIGEST)

    assert delta.digest.success is False
    assert delta.digest.reason == (
        "Verification reported success, but this turn built nothing and no "
        "step of the strategy is in VEuPathDB."
    )
    assert "built nothing" in delta.digest.prose
    assert delta.digest.caveats == [
        "The verification verdict was refused: this turn built nothing and no "
        "step of the strategy is in VEuPathDB",
    ]
    recorded = deps.state.domain.verification_digest
    assert recorded is not None
    assert recorded.success is False


async def test_success_over_a_real_build_stands(
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
        root_count=61,
    )

    delta = await _verify(monkeypatch, deps, _BUILD_DIGEST)

    assert delta.digest.success is True
    assert delta.digest.disposition is PhaseDisposition.DONE
    assert delta.digest.reason == "Verified successfully"
    assert delta.digest.caveats == []


def _combination_requirement() -> Constraint:
    return requirement(
        ConstraintKind.COMBINATION, "how the evidence combines", _COMBINATION
    )


def _combined_spec(operator: CombineOp) -> OperationalSpec:
    return OperationalSpec(
        goal="kinase drug targets",
        criteria=[
            Criterion(
                id="c_ms",
                text="trophozoite mass spectrometry evidence",
                search_name="GenesByMassSpec",
            ),
            Criterion(
                id="c_derisi",
                text="DeRisi timecourse expression",
                search_name="GenesByRNASeqEvidence",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=operator,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="c_ms"),
                    StructureNode(kind="leaf", criterion_id="c_derisi"),
                ],
            )
        ),
    )


def _combination_deps(operator: CombineOp) -> LeadDeps:
    state = pipeline_state(
        user_prompt="Kinases with mass spec evidence or DeRisi expression.",
    )
    state.domain.operational_spec = _combined_spec(operator)
    state.domain.requirements = [_combination_requirement()]
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"],
        wdk_strategy_id=330423363,
        root_count=12,
    )
    return lead_deps(
        state,
        strategy_session=_session_with_step(
            "plasmodb",
            name="Kinase drug targets",
            search_name="GenesByMassSpec",
            count=12,
            wdk_strategy_id=330423363,
        ),
    )


async def test_success_over_a_violated_combination_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _combination_deps(CombineOp.INTERSECT)

    delta = await _verify(monkeypatch, deps, _STRUCTURE_DIGEST)

    assert delta.digest.success is False
    assert delta.digest.failure_cause is FailureCause.STRUCTURE_VIOLATION
    assert _COMBINATION in delta.digest.reason
    assert "INTERSECT" in delta.digest.prose
    assert deps.state.turn_markers.verified is False


async def test_success_over_the_stated_combination_stands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _combination_deps(CombineOp.UNION)

    delta = await _verify(monkeypatch, deps, _STRUCTURE_DIGEST)

    assert delta.digest.success is True
    assert delta.digest.failure_cause is None
