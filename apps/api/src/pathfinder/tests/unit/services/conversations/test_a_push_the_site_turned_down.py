"""A canvas edit the site refused answers 502 and names what the site said."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.build_outcome import StepPushFailure
from pathfinder.platform.errors import AppError, ErrorCode
from pathfinder.services.conversations.strategy_ops import (
    refuse_a_push_the_site_turned_down,
)


def test_a_refused_step_is_a_502_that_names_the_site_error() -> None:
    failure = StepPushFailure(
        step_id="step_1a2b3c4d",
        search_name="GenesByOrthologs",
        error="Changes to answer param values are not allowed.",
        wdk_status=400,
    )

    with pytest.raises(AppError) as raised:
        refuse_a_push_the_site_turned_down([failure])

    error = raised.value
    assert error.status == 502
    assert error.code == ErrorCode.WDK_ERROR
    assert error.detail == (
        "The site did not accept the edit, so it was not applied: "
        "GenesByOrthologs: Changes to answer param values are not allowed."
    )


def test_every_refused_step_is_named() -> None:
    failures = [
        StepPushFailure(
            step_id="step_a", search_name="GenesByTaxon", error="bad organism"
        ),
        StepPushFailure(
            step_id="step_b", search_name="GenesByMassSpec", error="bad sample"
        ),
    ]

    with pytest.raises(AppError) as raised:
        refuse_a_push_the_site_turned_down(failures)

    assert raised.value.detail == (
        "The site did not accept the edit, so it was not applied: "
        "GenesByTaxon: bad organism; GenesByMassSpec: bad sample"
    )
