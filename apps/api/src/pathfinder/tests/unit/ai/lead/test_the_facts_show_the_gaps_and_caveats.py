"""The gaps and caveats of the check are shown beside the reply, so the reply
names a gap in words and restates no count."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic_ai import ModelRetry

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
    WordGap,
)
from pathfinder.domain.constraint_check import ConstraintCheck
from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    RequirementCheck,
    VerificationReview,
)
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    WithdrawnLifecycle,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.requirement_lifecycle import RetiredRequirement
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
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
_UNMET = RequirementGap(text="at least 2 transmembrane domains", status="unmet")
# The review row the check wrote, which the gap above is read from.
_UNMET_ROW = RequirementCheck(
    text="at least 2 transmembrane domains",
    turn=1,
    how="search",
    status="unmet",
    note="No step of the strategy reads it.",
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
            review=VerificationReview(requirements=[_UNMET_ROW] if gaps else []),
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


def _framed(word: str) -> LeadDeps:
    text = "all Plasmodium falciparum 3D7 genes, pseudogenes included"
    spec = OperationalSpec(
        goal=text,
        criteria=[
            Criterion(
                id="step_all",
                text=text,
                search_name="GenesByTaxon",
                search_display_name="Organism",
                role="seed",
                unexpressed_qualifiers=[word],
            )
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id="step_all")
        ),
    )
    state = pipeline_state(
        user_prompt=text,
        user_message_id=uuid4(),
        domain=StrategyDomainState(operational_spec=spec),
    )
    state.turn_markers.framed = True
    return lead_deps(state)


def test_a_framed_word_no_search_states_is_a_gap_without_a_check() -> None:
    assert turn_facts(_framed("pseudogenes")).gaps == [WordGap(word="pseudogenes")]


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


def _framed_nothing(monkeypatch: pytest.MonkeyPatch, unstated: list[str]) -> LeadDeps:
    async def _no_search(**_: Any) -> FrameResult:
        return FrameResult(
            disposition="needs_research",
            summary="No search on this site states a predicted GPI anchor.",
            unstated=unstated,
        )

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _no_search)
    return lead_deps(
        pipeline_state("plasmodb", user_prompt=_GPI_REQUEST, user_message_id=uuid4())
    )


@pytest.mark.asyncio
async def test_a_requirement_no_search_states_is_a_gap_with_nothing_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _framed_nothing(monkeypatch, ["predicted GPI anchor"])

    await run_frame(
        deps=deps, parent_tool_call_id="t1", work_order=frame_work_order("go", deps)
    )
    facts = turn_facts(deps)

    assert (facts.steps, facts.gaps) == (
        [],
        [RequirementGap(text="predicted GPI anchor", status="unexpressed")],
    )
    assert [gap.sentence for gap in facts.gaps] == [
        "'predicted GPI anchor': no search on this site states it"
    ]


@pytest.mark.asyncio
async def test_a_requirement_the_researcher_did_not_state_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _framed_nothing(monkeypatch, ["glycosylphosphatidylinositol anchor"])

    with pytest.raises(ModelRetry, match="glycosylphosphatidylinositol anchor"):
        await run_frame(
            deps=deps,
            parent_tool_call_id="t1",
            work_order=frame_work_order("go", deps),
        )
    assert turn_facts(deps).gaps == []


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
            constraint_report=[
                ConstraintCheck(
                    step_id="step_a036deb7",
                    label="fold change",
                    requested="1.5",
                    realized="2.82843",
                    honored=False,
                ),
                ConstraintCheck(
                    step_id="step_a036deb7",
                    label="significance",
                    requested="0.05",
                    realized="0.05",
                    honored=True,
                ),
            ],
        ),
        revision=strategy_revision(None),
    )

    facts = turn_facts(lead_deps(state))

    assert [gap.sentence for gap in facts.gaps] == [
        "Not met: fold change asked 1.5, built 2.82843"
    ]
    assert "Not met: fold change asked 1.5, built 2.82843" in facts.lines()
