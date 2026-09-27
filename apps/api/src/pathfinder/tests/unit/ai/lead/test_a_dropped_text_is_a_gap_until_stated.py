"""A text the organism fold drops as unexpressed stays a gap on the spec's own
drop record until a criterion of the spec states it."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.lead.ledger_render import render_frame_full
from pathfinder.ai.lead.ledger_sections import (
    FrameSection,
    unexpressed_constraints,
    unexpressed_words,
)
from pathfinder.ai.lead.verify_review import ReviewRecord, review_held_to_the_turn
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import ConstraintStatus
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec

PF = "Plasmodium falciparum 3D7"
_ISOLATES = "do not vary much between isolates"
_ASKED = f"Genes with a signal peptide that {_ISOLATES}."
_FATE = (
    f"c_isolates ('{_ISOLATES}') is dropped: its search sets only the organism "
    f"{PF}, which c_signal already runs on, so it narrows nothing. '{_ISOLATES}' "
    f"is recorded unexpressed: bind a search whose values state it, or end with "
    f"it as a gap."
)


def _signal(version: str = "SignalP-6.0") -> Criterion:
    return Criterion(
        id="c_signal",
        text="proteins with a predicted signal peptide",
        search_name="GenesWithSignalPeptide",
        organism_param="organism",
        resolved_params={
            "organism": MultiPickValue(values=[PF]),
            "signalp_version": SinglePickValue(value=version),
        },
    )


def _snps(criterion_id: str, text: str, stat: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=text,
        search_name="GenesByNgsSnps",
        organism_param="organismSinglePick",
        resolved_params={
            "organismSinglePick": MultiPickValue(values=[PF]),
            "snp_stat": StringValue(value=stat),
        },
    )


def _after_the_drop(*, unexpressed: bool = True) -> AgentToolState:
    state = AgentToolState()
    state.frame_set_criterion(_signal())
    state.frame_set_criterion(_snps("c_isolates", _ISOLATES, "density"))
    state.frame_drop_criterion("c_isolates", _FATE, unexpressed=unexpressed)
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


def test_the_ledger_blocks_on_the_dropped_text_and_lists_the_drop() -> None:
    spec = _after_the_drop().operational_spec_draft

    [grounded] = unexpressed_constraints(spec)

    assert (
        grounded.constraint.requested_value,
        grounded.status,
        grounded.note,
    ) == (_ISOLATES, ConstraintStatus.UNGROUNDABLE, _FATE)
    assert unexpressed_words(spec) == [_ISOLATES]
    assert f"- {_ISOLATES} - {_FATE}" in render_frame_full(FrameSection(spec=spec))


def test_a_drop_the_organism_meets_is_no_gap() -> None:
    spec = _after_the_drop(unexpressed=False).operational_spec_draft

    assert (unexpressed_words(spec), unexpressed_constraints(spec)) == ([], [])
