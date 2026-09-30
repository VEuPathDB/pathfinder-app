"""The requirement a dropped criterion restated stays open on the spec's drop
record, and is a gap in the researcher's words until a criterion states it."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.ledger_render import render_frame_full
from pathfinder.ai.lead.ledger_sections import (
    FrameSection,
    unexpressed_constraints,
    unexpressed_words,
)
from pathfinder.ai.lead.verify_review import ReviewRecord, review_held_to_the_turn
from pathfinder.domain.caveats import WordGap, check_gaps
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    OpenLifecycle,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state

PF = "Plasmodium falciparum 3D7"
_ISOLATES = "do not vary much between isolates"
_ASKED = f"Genes with a signal peptide that {_ISOLATES}."
# The criterion's own text, which is the plan's words and never a gap.
_PLAN = "SNP density at the site default across isolates"
_REQUIREMENT = Constraint(
    kind=ConstraintKind.OTHER,
    requested_value=_ISOLATES,
    label="little variation between isolates",
    source=ConstraintSource.USER_EXPLICIT,
)
_FATE = (
    f"c_isolates ('{_PLAN}') is dropped: it matches all 5,720 genes of {PF}, "
    f"which c_signal already runs on, so it narrows nothing. '{_ISOLATES}' stays "
    f"open: bind a search whose values state it, or end with it as a gap."
)


def _signal(version: str = "SignalP-6.0") -> Criterion:
    return Criterion(
        id="c_signal",
        text="proteins with a predicted signal peptide",
        search_name="GenesWithSignalPeptide",
        organism_param="organism",
        resolved_params=bound(
            {
                "organism": MultiPickValue(values=[PF]),
                "signalp_version": SinglePickValue(value=version),
            }
        ),
    )


def _snps(criterion_id: str, text: str, stat: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=text,
        search_name="GenesByNgsSnps",
        organism_param="organismSinglePick",
        resolved_params=bound(
            {
                "organismSinglePick": MultiPickValue(values=[PF]),
                "snp_stat": StringValue(value=stat),
            }
        ),
    )


def _after_the_drop(requirement: Constraint | None = _REQUIREMENT) -> AgentToolState:
    state = AgentToolState()
    state.frame_set_criterion(_signal())
    state.frame_set_criterion(_snps("c_isolates", _PLAN, "density"))
    state.frame_drop_criterion("c_isolates", _FATE, requirement=requirement)
    return state


def _record(spec: OperationalSpec) -> ReviewRecord:
    return ReviewRecord(
        messages=(_ASKED,),
        requirements=(),
        spec=spec,
        read_as=lambda _reference: None,
        record_url=lambda gene_id: gene_id,
    )


def test_rebinding_the_criterion_it_ran_beside_keeps_the_gap() -> None:
    state = _after_the_drop()
    state.frame_set_criterion(_signal("SignalP-4.1"))

    held = review_held_to_the_turn(
        VerificationReview(), _record(state.operational_spec_draft)
    )

    assert held.requirements == [
        RequirementCheck(
            text=_ISOLATES,
            turn=1,
            how="search",
            status="unexpressed",
            note=f"no search the framing pass read can state '{_ISOLATES}'",
        )
    ]


def test_a_criterion_that_states_the_text_meets_it() -> None:
    state = _after_the_drop()
    state.frame_set_criterion(_snps("c_diversity", f"genes that {_ISOLATES}", "pi"))
    met = RequirementCheck(
        text=_ISOLATES,
        turn=1,
        answered_by=["c_diversity"],
        how="parameter",
        status="met",
        note="the diversity statistic states it",
    )

    spec = state.operational_spec_draft
    held = review_held_to_the_turn(
        VerificationReview(requirements=[met]), _record(spec)
    )

    assert held.requirements == [met]
    assert unexpressed_words(spec) == []


def test_the_ledger_blocks_on_the_requirement_and_lists_the_drop() -> None:
    spec = _after_the_drop().operational_spec_draft

    [grounded] = unexpressed_constraints(spec)

    assert (
        grounded.constraint,
        grounded.status,
        grounded.note,
        grounded.lifecycle,
    ) == (_REQUIREMENT, ConstraintStatus.UNGROUNDABLE, _FATE, OpenLifecycle())
    assert unexpressed_words(spec) == [_ISOLATES]
    assert f"- {_PLAN} - {_FATE}" in render_frame_full(FrameSection(spec=spec))


def test_the_gap_is_the_requirement_never_the_criterion_text() -> None:
    spec = _after_the_drop().operational_spec_draft

    gaps = check_gaps(
        structure=None,
        words=unexpressed_words(spec),
        review=VerificationReview(),
        requirements=unexpressed_constraints(spec),
    )

    assert gaps == [WordGap(word=_ISOLATES)]


def test_a_drop_that_holds_no_requirement_open_is_no_gap() -> None:
    spec = _after_the_drop(requirement=None).operational_spec_draft

    assert (unexpressed_words(spec), unexpressed_constraints(spec)) == ([], [])


def test_the_ledger_holds_the_stated_requirement_once_and_unmet() -> None:
    state = pipeline_state(user_prompt=_ASKED)
    state.domain.requirements = [_REQUIREMENT]
    state.domain.operational_spec = _after_the_drop().operational_spec_draft

    grounded = derive_ledger(state, None).constraints.grounded

    assert [
        (g.constraint, g.status) for g in grounded if g.constraint == _REQUIREMENT
    ] == [(_REQUIREMENT, ConstraintStatus.UNGROUNDABLE)]
