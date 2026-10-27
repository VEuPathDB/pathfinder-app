"""The gaps and caveats of the check are shown beside the reply, so the reply
names a gap in words and restates no count."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead import frame_dispatch
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_dispatch import frame_work_order, run_frame
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.caveats import (
    Caveat,
    ControlsCaveat,
    Gap,
    RequirementGap,
)
from pathfinder.domain.evidence import ControlSetEvidence, ControlTestEvidence
from pathfinder.domain.site_checks import SiteCheck, SiteCheckGap
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    WithdrawnLifecycle,
)
from pathfinder.domain.strategy.requirement_lifecycle import RetiredRequirement
from pathfinder.domain.strategy.requirement_reports import (
    ReportedRequirement,
    RequirementProblem,
    RequirementReport,
)
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
    site_lacks,
)

_POSITIVES = [f"PF3D7_01{n:05d}" for n in range(80)]
_NEGATIVES = [f"PF3D7_14{n:05d}" for n in range(40)]
_V2_TEST = ControlTestEvidence(
    tested_label="Predicted Signal Peptide",
    positive=ControlSetEvidence(returned=_POSITIVES[:52], not_returned=_POSITIVES[52:]),
    negative=ControlSetEvidence(returned=_NEGATIVES[:2], not_returned=_NEGATIVES[2:]),
)
_V2_CAVEAT = ControlsCaveat(
    positives_returned=52, positives_total=80, negatives_returned=2, negatives_total=40
)
_UNMET = SiteCheckGap(
    check=SiteCheck(
        kind=ConstraintKind.OTHER,
        subject="at least 2 transmembrane domains",
        status="fail",
        evidence="the strategy states tm_count = 1",
        requirement="other:at least 2 transmembrane domains",
    )
)


def _checked(
    *, gaps: list[Gap] | None = None, caveats: list[Caveat] | None = None
) -> LeadDeps:
    state = pipeline_state(
        user_prompt="Test this strategy against my controls.",
        user_message_id=uuid4(),
    )
    state.domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="controls tested",
            success=True,
            gaps=gaps or [],
            caveats=caveats or [],
        ),
        revision=strategy_revision(None),
    )
    state.domain.requirements = [
        requirement(
            ConstraintKind.OTHER,
            "transmembrane domains",
            "at least 2 transmembrane domains",
        )
    ]
    state.turn_markers.verification_dispatched = True
    state.turn_markers.control_tests.append(
        ControlTestRun(tool_call_id="call_controls", evidence=_V2_TEST)
    )
    return lead_deps(state)


def test_the_checks_gaps_and_caveats_are_shown_beside_the_reply() -> None:
    facts = turn_facts(_checked(gaps=[_UNMET], caveats=[_V2_CAVEAT]))

    assert (facts.gaps, facts.caveats) == ([_UNMET], [_V2_CAVEAT])
    assert [r.sentence for r in facts.control_results] == [
        (
            "Predicted Signal Peptide: 52 of 80 positive controls returned; "
            "2 of 40 negative controls returned"
        )
    ]


def test_a_reply_that_names_the_gap_in_words_stands() -> None:
    report = reply(
        "The strategy does not require the transmembrane domains you asked for; "
        "the shortfall and the control results are shown beside this reply."
    )

    assert kinds(_checked(gaps=[_UNMET], caveats=[_V2_CAVEAT]), report) == []


def test_a_gap_a_requirement_the_researcher_withdrew_names_is_no_gap() -> None:
    deps = _checked(gaps=[_UNMET])
    deps.state.domain.retired_requirements = [
        RetiredRequirement(
            constraint=Constraint(
                kind=ConstraintKind.OTHER,
                label="transmembrane domains",
                requested_value="at least 2 transmembrane domains",
                source=ConstraintSource.USER_EXPLICIT,
            ),
            lifecycle=WithdrawnLifecycle(turn_id="t2"),
        )
    ]
    facts = turn_facts(deps)

    assert facts.gaps == []
    assert [r.sentence for r in facts.retired] == [
        "'at least 2 transmembrane domains' is withdrawn"
    ]


_GPI_REQUEST = "Find Plasmodium falciparum 3D7 genes with a predicted GPI anchor"


_GPI = Constraint(
    kind=ConstraintKind.OTHER,
    label="predicted GPI anchor",
    requested_value="predicted GPI anchor",
    source=ConstraintSource.USER_EXPLICIT,
)


def _framed_nothing(
    monkeypatch: pytest.MonkeyPatch,
    reports: list[RequirementReport],
    held: list[Constraint],
) -> LeadDeps:
    async def _no_search(**_: Any) -> FrameResult:
        return FrameResult(
            disposition="needs_research",
            summary=(
                "No search on this site states a predicted GPI anchor; the "
                "nearest is the text search, which reads annotation words."
            ),
            requirement_problems=reports,
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _no_search)
    return lead_deps(
        pipeline_state(
            "plasmodb",
            user_prompt=_GPI_REQUEST,
            user_message_id=uuid4(),
            domain=StrategyDomainState(requirements=held),
        )
    )


async def _facts_after_framing(deps: LeadDeps) -> TurnFacts:
    await run_frame(
        deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
    )
    return turn_facts(deps)


@pytest.mark.asyncio
async def test_a_requirement_the_site_lacks_is_a_gap_in_the_held_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = await _facts_after_framing(
        _framed_nothing(monkeypatch, site_lacks("R1"), [_GPI])
    )

    assert (facts.steps, facts.gaps) == (
        [],
        [RequirementGap(text="predicted GPI anchor")],
    )
    assert [gap.sentence for gap in facts.gaps] == [
        "'predicted GPI anchor': no search on this site states it"
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem",
    [
        RequirementProblem.STAND_IN_BOUND,
        RequirementProblem.NEEDS_THE_ANALYSIS_WORKFLOW,
        RequirementProblem.REQUEST_LEAVES_IT_OPEN,
    ],
)
async def test_a_report_of_another_problem_is_carried_and_is_no_gap(
    monkeypatch: pytest.MonkeyPatch, problem: RequirementProblem
) -> None:
    report = RequirementReport(requirement="R1", problem=problem)
    deps = _framed_nothing(monkeypatch, [report], [_GPI])

    result = await run_frame(
        deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
    )

    assert isinstance(result, FrameResult)
    assert result.reported == [
        ReportedRequirement(requirement="predicted GPI anchor", problem=problem)
    ]
    assert "requirementProblems" not in result.model_dump(by_alias=True)
    assert turn_facts(deps).gaps == []


@pytest.mark.asyncio
async def test_a_number_the_list_lacks_is_no_gap_and_ends_no_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = await _facts_after_framing(
        _framed_nothing(monkeypatch, site_lacks("R1"), [])
    )

    assert facts.gaps == []


_FOLD = SiteCheck(
    kind=ConstraintKind.FOLD_CHANGE,
    subject="1.5-fold",
    status="fail",
    evidence="1.5-fold, built 2.82843-fold (log2 1.5)",
    requirement="fold_change:1.5-fold",
)
_FOLD_SENTENCE = "'1.5-fold': 1.5-fold, built 2.82843-fold (log2 1.5)"


def test_a_study_step_check_short_of_the_request_is_a_facts_row() -> None:
    state = pipeline_state(
        user_prompt="loosen the fold change to 1.5-fold", user_message_id=uuid4()
    )
    state.domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="the study step was read",
            success=False,
            gaps=[SiteCheckGap(check=_FOLD)],
        ),
        revision=strategy_revision(None),
    )

    facts = turn_facts(lead_deps(state))

    assert [gap.sentence for gap in facts.gaps] == [_FOLD_SENTENCE]
    assert _FOLD_SENTENCE in facts.lines()
