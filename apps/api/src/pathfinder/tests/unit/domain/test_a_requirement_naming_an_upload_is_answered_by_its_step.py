"""A requirement that names the researcher's upload is answered by the step that
runs on that upload, whatever the check filed for it."""

from __future__ import annotations

from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.shown_requirements import answered_by_uploads

# The DESeq flow on plasmodb: one step, run on the upload the message names.
_STEP = "step_cb47c568"
_NAMES_THE_UPLOAD = RequirementCheck(
    text="On my uploaded RNA-Seq dataset 'pathfinder-uat-deseq'",
    turn=1,
    how="parameter",
    status="unmet",
    note=(
        "The strategy uses uploaded study `EDAUD_lhZ5ptRgo014J`, but the RNA-Seq "
        "data-type requirement is ungroundable and is not established by the "
        "strategy."
    ),
)
_DESEQ = RequirementCheck(
    text="with DESeq2",
    turn=1,
    answered_by=[_STEP],
    how="parameter",
    status="met",
    note="`differentialExpressionMethod` is `DESeq`.",
)


def test_the_row_naming_the_upload_is_met_by_the_step_that_runs_on_it() -> None:
    review = VerificationReview(requirements=[_NAMES_THE_UPLOAD, _DESEQ])

    held = answered_by_uploads(review, {_STEP: "pathfinder-uat-deseq"})

    assert [(r.text, r.status, r.answered_by, r.note) for r in held.requirements] == [
        (
            "On my uploaded RNA-Seq dataset 'pathfinder-uat-deseq'",
            "met",
            [_STEP],
            "The step runs on the upload 'pathfinder-uat-deseq'.",
        ),
        ("with DESeq2", "met", [_STEP], "`differentialExpressionMethod` is `DESeq`."),
    ]


def test_a_row_naming_an_upload_no_step_runs_on_stays_as_filed() -> None:
    review = VerificationReview(requirements=[_NAMES_THE_UPLOAD])

    assert answered_by_uploads(review, {_STEP: "pathfinder-uat-genelist"}) == review
