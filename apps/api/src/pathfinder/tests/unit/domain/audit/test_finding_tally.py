"""What a tally row may say, and the run counts its rows add up to."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from pathfinder.domain.audit.findings import (
    ErrorType,
    FindingCounts,
    FindingStatus,
    FindingTally,
    counts_of,
)


@pytest.mark.parametrize(
    ("status", "error_type"),
    [("failed", None), ("unsampled", None), ("confirmed", "truncated_model")],
)
def test_only_a_confirmed_finding_naming_no_error_can_be_unjudged(
    status: FindingStatus, error_type: ErrorType | None
) -> None:
    with pytest.raises(ValidationError, match="not judged"):
        FindingTally(
            genome="G",
            check="gene_length",
            status=status,
            error_type=error_type,
            judged=False,
            count=1,
            model_genome="G",
        )
    assert FindingTally(
        genome="G",
        check="gene_length",
        status="confirmed",
        error_type=None,
        count=1,
        judged=True,
        model_genome="G",
    ).judged


def test_counts_add_each_status_and_the_named_errors() -> None:
    tally = [
        FindingTally(
            genome="G",
            check="gene_length",
            status="confirmed",
            error_type="truncated_model",
            count=2,
            judged=True,
            model_genome="G",
        ),
        FindingTally(
            genome="G",
            check="gene_length",
            status="confirmed",
            error_type=None,
            count=5,
            judged=True,
            model_genome="G",
        ),
        FindingTally(
            genome="G",
            check="gene_split",
            status="unsampled",
            error_type=None,
            count=7,
            judged=True,
            model_genome="G",
        ),
        FindingTally(
            genome="",
            check="pseudogene_call",
            status="failed",
            error_type=None,
            count=1,
            judged=True,
            model_genome="",
        ),
        FindingTally(
            genome="",
            check="pseudogene_call",
            status="unreached",
            error_type=None,
            count=1,
            judged=True,
            model_genome="",
        ),
        FindingTally(
            genome="G",
            check="gene_split",
            status="unread",
            error_type=None,
            count=4,
            judged=True,
            model_genome="G",
        ),
        FindingTally(
            genome="G",
            check="missing_gene",
            status="confirmed",
            error_type=None,
            judged=False,
            count=3,
            model_genome="G",
        ),
    ]
    assert counts_of(tally) == FindingCounts(
        confirmed=10, unsampled=7, failed=1, unreached=1, unread=4, errors=2, unjudged=3
    )
