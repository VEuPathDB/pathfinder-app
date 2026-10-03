"""A verification verdict never says more than the build or the structure holds.

A success over a build that pushed nothing, or over a tree that answers another
question, is rewritten to the failure the ledger holds.
"""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep

from pathfinder.ai.graph.state import FailureCause, PhaseDisposition
from pathfinder.ai.lead import sub_agent_tools
from pathfinder.ai.lead.answered_strategy import live_tree
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.caveats import BuildCaveat, StructureGap
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.revision import strategy_revision
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
        "Verification reported success, and the ledger records what the strategy "
        "does not answer."
    )
    assert delta.digest.prose.startswith(
        "Verification cannot be reported: The build pushed 0 steps, failed 0, "
        "skipped 0 and left 0 empty."
    )
    assert delta.digest.caveats == [BuildCaveat(pushed=0, failed=0, skipped=0, empty=0)]
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
    )

    delta = await _verify(monkeypatch, deps, _BUILD_DIGEST)

    assert delta.digest.success is True
    assert delta.digest.disposition is PhaseDisposition.DONE
    assert delta.digest.reason == "Verified successfully"
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
    assert delta.digest.gaps == [
        StructureGap(expression=_COMBINATION, built="INTERSECT")
    ]
    assert deps.state.turn_markers.verified is False


async def test_success_over_the_stated_combination_stands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _combination_deps(CombineOp.UNION)

    delta = await _verify(monkeypatch, deps, _STRUCTURE_DIGEST)

    assert delta.digest.success is True
    assert delta.digest.failure_cause is None


_PASSED = "every stated requirement is met by a step and the records show it"


def _genes_row(**marks: bool) -> dict[str, Any]:
    return {
        "text": "genes",
        "turn": 1,
        "answeredBy": [],
        "how": "parameter",
        "status": "unmet",
        "note": "The strategy record type is `transcript`, not `gene`.",
        **marks,
    }


def _transcript_digest(*rows: dict[str, Any]) -> dict[str, Any]:
    return {
        "digest": {
            "disposition": "handoff",
            "handoffTo": "frame",
            "success": False,
            "prose": (
                "The predicted signal-peptide search returned **720** records. The "
                "strategy is configured as `transcript` record type rather than "
                "`gene`, so the requested data type is not verified as honored."
            ),
            "reason": (
                "The search returns a plausible 720-record result, but its "
                "configured record type is `transcript`, not the requested genes."
            ),
            "review": {"requirements": list(rows)},
        }
    }


def _signal_peptide_deps() -> LeadDeps:
    state = pipeline_state(
        "toxodb",
        user_prompt=(
            "Find Toxoplasma gondii ME49 genes whose proteins have a predicted "
            "signal peptide."
        ),
    )
    state.domain.operational_spec = OperationalSpec(
        goal="signal peptide genes",
        record_type="transcript",
        criteria=[
            Criterion(
                id="s1",
                text="proteins have a predicted signal peptide",
                search_name="GenesWithSignalPeptide",
            )
        ],
    )
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"], wdk_strategy_id=330885923
    )
    return lead_deps(
        state,
        strategy_session=_session_with_step(
            "toxodb",
            name="Signal peptide",
            search_name="GenesWithSignalPeptide",
            count=720,
            wdk_strategy_id=330885923,
        ),
    )


async def test_a_failure_the_rows_do_not_support_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _signal_peptide_deps()

    delta = await _verify(monkeypatch, deps, _transcript_digest(_genes_row()))

    digest = delta.digest
    assert [(r.text, r.shown_status) for r in digest.review.requirements] == [
        ("genes", "met")
    ]
    assert (digest.success, digest.failure_cause, digest.gaps) == (True, None, [])
    assert digest.reason == f"Verification passed: {_PASSED}."
    assert (digest.disposition, digest.handoff_to) == (PhaseDisposition.DONE, None)
    assert deps.state.turn_markers.verified is True


async def test_a_failure_with_a_row_no_record_shows_stays_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unshown = {
        "text": "proteins have a predicted signal peptide",
        "turn": 1,
        "answeredBy": ["s1"],
        "how": "search",
        "status": "met",
        "noRecordShowsIt": True,
    }

    delta = await _verify(
        monkeypatch,
        _signal_peptide_deps(),
        _transcript_digest(_genes_row(), unshown),
    )

    assert [r.shown_status for r in delta.digest.review.requirements] == [
        "met",
        "unshown",
    ]
    assert delta.digest.success is False
    assert delta.digest.reason.startswith("The search returns a plausible 720-record")
