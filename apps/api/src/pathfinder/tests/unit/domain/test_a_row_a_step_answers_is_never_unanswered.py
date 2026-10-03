"""A requirement a step answers is never reported as one nothing answers: the
type refuses an unmet row that names a step, and a met row whose sampled
records are all unclear is met, or unjudged when only a text query answers it."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.caveats import Gap, RequirementGap, check_gaps
from pathfinder.domain.evidence import (
    RequirementCheck,
    SampledGene,
    VerificationReview,
)
from pathfinder.domain.shown_requirements import TextQuery, held_to_the_records
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
)

# plasmodb: the PlasmoAP apicoplast list step, and eight records a check read.
_TEXT = "predicted apicoplast targeting signal"
_PLASMOAP_STEP = "step_33f64941"
_UNCLEAR = [
    SampledGene(
        gene_id=gene_id,
        fits="unclear",
        why="The product description does not state a predicted apicoplast-"
        "targeting signal.",
    )
    for gene_id in (
        "PF3D7_0214800",
        "PF3D7_0301700",
        "PF3D7_0701500",
        "PF3D7_0918000",
        "PF3D7_1039900",
        "PF3D7_1214800",
        "PF3D7_1337200",
        "PF3D7_1357200",
    )
]
_HELD = [
    GroundedConstraint(
        constraint=Constraint(
            kind=ConstraintKind.OTHER,
            requested_value=_TEXT,
            label=_TEXT,
            source=ConstraintSource.USER_EXPLICIT,
        ),
        status=ConstraintStatus.GROUNDED,
    )
]


def _row(status: str) -> RequirementCheck:
    return RequirementCheck.model_validate(
        {
            "text": _TEXT,
            "turn": 1,
            "answeredBy": [_PLASMOAP_STEP],
            "how": "parameter",
            "status": status,
        }
    )


def _gaps(queries: list[TextQuery]) -> tuple[str, list[Gap]]:
    review = held_to_the_records(
        VerificationReview(requirements=[_row("met")], sampled_genes=_UNCLEAR),
        queries,
    )
    return (
        review.requirements[0].shown_status,
        check_gaps(structure=None, words=[], review=review, requirements=_HELD),
    )


def test_an_unmet_row_that_names_its_step_is_refused() -> None:
    with pytest.raises(ValidationError, match="an unmet requirement names no step"):
        _row("unmet")


def test_a_list_step_with_every_record_unclear_is_met_and_no_gap() -> None:
    assert _gaps([]) == ("met", [])


def test_a_text_step_with_every_record_unclear_is_unjudged() -> None:
    status, gaps = _gaps(
        [TextQuery(criterion_id=_PLASMOAP_STEP, param="text_expression", value=_TEXT)]
    )

    assert (status, gaps) == (
        "unjudged",
        [RequirementGap(text=_TEXT, status="unjudged")],
    )
    assert [(g.sentence, g.fails_the_check) for g in gaps] == [
        ("'predicted apicoplast targeting signal': no sampled record judged it", False)
    ]
