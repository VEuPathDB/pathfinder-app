from __future__ import annotations

import json
from pathlib import Path

from strategist.domain.strategy.constraint_grounding import ground_against_spec
from strategist.domain.strategy.constraints import Constraint, ConstraintStatus
from strategist.domain.strategy.data_marks import DataMarks
from strategist.domain.strategy.operational_spec import OperationalSpec
from strategist.domain.unread import Unread

_B1 = json.loads(
    (
        Path(__file__).resolve().parents[3]
        / "fixtures"
        / "turns"
        / "b1_pexel_rna_seq_frame.json"
    ).read_text()
)
_SPEC = OperationalSpec.model_validate(_B1["spec"])
_R5 = Constraint.model_validate(_B1["requirements"][4])
_NEWBOLD = "GenesByRNASeqpfal3D7_Newbold_ebi_rnaSeq_RSRCPercentile"
_PEXEL = "GenesBySubcellularLocalizationpfal3D7_subcellular_localization_Cowman_RSRC"


def _ground(marks: DataMarks) -> tuple[object, ...]:
    [grounded] = ground_against_spec([_R5], _SPEC, marks=marks)
    return grounded.status, grounded.unverified, grounded.realized_value


def test_marks_read_for_another_spec_leave_the_data_type_not_verified() -> None:
    assert _ground(DataMarks()) == (
        ConstraintStatus.NOT_VERIFIED,
        "no_value_to_compare",
        None,
    )


def test_a_mark_whose_read_failed_leaves_the_data_type_not_verified() -> None:
    marks = DataMarks(
        searches={_NEWBOLD: Unread(reason="the site's catalog did not answer")},
        read_for=frozenset({_NEWBOLD, _PEXEL}),
    )

    [grounded] = ground_against_spec([_R5], _SPEC, marks=marks)

    assert (grounded.status, grounded.note) == (
        ConstraintStatus.NOT_VERIFIED,
        "the site's catalog did not answer",
    )


def test_marks_read_for_the_spec_ground_the_data_type() -> None:
    marks = DataMarks(
        searches={_NEWBOLD: "RNASeq"}, read_for=frozenset({_NEWBOLD, _PEXEL})
    )

    assert _ground(marks) == (ConstraintStatus.GROUNDED, None, "rna_seq")


def test_a_search_read_with_no_mark_runs_on_no_expression_data() -> None:
    marks = DataMarks(read_for=frozenset({_NEWBOLD, _PEXEL}))

    assert _ground(marks) == (ConstraintStatus.UNGROUNDABLE, None, None)


def test_an_upload_whose_listing_failed_leaves_the_data_type_not_verified() -> None:
    upload = _SPEC.criteria[1].id
    marks = DataMarks(
        uploads={upload: Unread(reason="your uploads were not read")},
        read_for=frozenset({_NEWBOLD, _PEXEL}),
    )

    [grounded] = ground_against_spec([_R5], _SPEC, marks=marks)

    assert (grounded.status, grounded.note) == (
        ConstraintStatus.NOT_VERIFIED,
        "your uploads were not read",
    )
