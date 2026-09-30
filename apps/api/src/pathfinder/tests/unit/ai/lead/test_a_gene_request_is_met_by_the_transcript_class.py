"""A request for genes is met by a strategy on the transcript class: the site
counts a transcript answer in genes."""

from __future__ import annotations

from pathfinder.ai.lead.verify_review import ReviewRecord, review_held_to_the_turn
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests.unit.ai.lead.conftest import requirement

_ASKED = "Aedes aegypti LVP_AGWG odorant-binding protein genes on chromosome 3."


def _spec(record_type: str) -> OperationalSpec:
    return OperationalSpec(
        goal="odorant-binding proteins on chromosome 3",
        record_type=record_type,
        criteria=[
            Criterion(
                id="c_obp",
                text="odorant-binding protein",
                search_name="GenesByInterproDomain",
            ),
            Criterion(id="c_chr3", text="chromosome 3", search_name="GenesByLocation"),
        ],
    )


def _record(spec: OperationalSpec) -> ReviewRecord:
    return ReviewRecord(
        messages=(_ASKED,),
        requirements=(requirement(ConstraintKind.RECORD_TYPE, "record type", "genes"),),
        spec=spec,
        read_as=lambda reference: None,
        record_url=lambda gene_id: gene_id,
    )


_GENES_ROW = RequirementCheck(
    text="genes",
    turn=1,
    how="parameter",
    status="unmet",
    note="The built strategy's record type is transcript, not genes.",
)


def test_genes_is_met_by_the_transcript_class() -> None:
    held = review_held_to_the_turn(
        VerificationReview(requirements=[_GENES_ROW]), _record(_spec("transcript"))
    )

    row = held.requirements[0]
    assert (row.status, row.answered_by, row.note) == (
        "met",
        ["c_obp", "c_chr3"],
        "the strategy returns genes",
    )


def test_a_class_counted_in_another_noun_leaves_the_row() -> None:
    held = review_held_to_the_turn(
        VerificationReview(requirements=[_GENES_ROW]), _record(_spec("snp"))
    )

    assert held.requirements == [_GENES_ROW]
