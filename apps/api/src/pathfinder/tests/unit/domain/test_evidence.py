"""The evidence card's values agree with the lists and counts they are read from."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pathfinder.domain.evidence import (
    CheckedStepCount,
    ControlEnrichment,
    ControlSetEvidence,
    ControlTestEvidence,
    EvidenceCard,
    EvidenceVerdict,
)

_RECOVERED = [f"PF3D7_{index:07d}" for index in range(7)]
_MISSED = ["PF3D7_0000007", "PF3D7_0000008", "PF3D7_0000009"]
_ADMITTED = ["PF3D7_1000000"]
_EXCLUDED = [f"PF3D7_{index:07d}" for index in range(1000001, 1000012)]


def _positive() -> ControlSetEvidence:
    return ControlSetEvidence(returned=_RECOVERED, not_returned=_MISSED)


def _negative() -> ControlSetEvidence:
    return ControlSetEvidence(returned=_ADMITTED, not_returned=_EXCLUDED)


def test_a_control_set_reads_its_counts_from_its_lists() -> None:
    dumped = _positive().model_dump(by_alias=True)

    assert dumped["controlsCount"] == 10
    assert dumped["returnedCount"] == 7
    assert dumped["rate"] == pytest.approx(0.7)


def test_a_control_set_with_no_id_is_refused() -> None:
    with pytest.raises(ValidationError, match="at least one id"):
        ControlSetEvidence(returned=[], not_returned=[])


def test_an_id_filed_on_both_lists_is_refused() -> None:
    with pytest.raises(ValidationError, match="PF3D7_0000007"):
        ControlSetEvidence(
            returned=["PF3D7_0000007"], not_returned=["PF3D7_0000007", "PF3D7_1"]
        )


def _enrichment(**changes: int | float) -> ControlEnrichment:
    fields: dict[str, int | float] = {
        "population": 22,
        "positives": 10,
        "returned": 8,
        "positives_returned": 7,
        "p_value": 0.00297,
    }
    fields.update(changes)
    return ControlEnrichment.model_validate(fields)


def test_the_enrichment_row_matches_the_two_sets_it_reads() -> None:
    tested = ControlTestEvidence(
        tested_label="Genes by Molecular Weight",
        wdk_step_id=440299573,
        positive=_positive(),
        negative=_negative(),
        enrichment=_enrichment(),
    )

    assert tested.enrichment is not None
    assert tested.enrichment.positives_returned == 7


def test_an_enrichment_whose_counts_differ_from_the_sets_is_refused() -> None:
    with pytest.raises(ValidationError, match="enrichment"):
        ControlTestEvidence(
            tested_label="Genes by Molecular Weight",
            positive=_positive(),
            negative=_negative(),
            enrichment=_enrichment(positives_returned=8),
        )


def test_an_enrichment_needs_both_kinds() -> None:
    with pytest.raises(ValidationError, match="both"):
        ControlTestEvidence(
            tested_label="Genes by Molecular Weight",
            positive=_positive(),
            enrichment=_enrichment(),
        )


def test_a_test_with_no_control_set_is_refused() -> None:
    with pytest.raises(ValidationError, match="control set"):
        ControlTestEvidence(tested_label="Genes by Molecular Weight")


@pytest.mark.parametrize(
    ("recorded", "site", "drifted"),
    [(132, 132, False), (132, 140, True), (None, 140, False), (132, None, False)],
)
def test_a_step_drifted_only_when_both_counts_exist_and_differ(
    recorded: int | None, site: int | None, drifted: bool
) -> None:
    step = CheckedStepCount(
        step_id="s1",
        wdk_step_id=440299573,
        title="Genes by Molecular Weight",
        recorded_count=recorded,
        site_count=site,
    )

    assert step.model_dump(by_alias=True)["drifted"] is drifted


def test_the_card_lists_every_text_a_reader_can_see() -> None:
    card = EvidenceCard(
        check_id="call_verify",
        revision="rev-1",
        site_id="plasmodb",
        checked_at=datetime(2026, 9, 24, 9, 0, tzinfo=UTC),
        wdk_strategy_id=300,
        strategy_url="https://plasmodb.org/plasmo/app/workspace/strategies/300/7",
        site_read="read",
        steps=[
            CheckedStepCount(
                step_id="s1",
                wdk_step_id=7,
                title="Genes by Molecular Weight",
                recorded_count=132,
                site_count=132,
            )
        ],
        controls=[
            ControlTestEvidence(tested_label="the tested step", positive=_positive())
        ],
        citations=[],
        verdict=EvidenceVerdict(
            supported=False, refused_because="this turn built nothing"
        ),
    )

    assert card.texts() == [
        "https://plasmodb.org/plasmo/app/workspace/strategies/300/7",
        "this turn built nothing",
        "Genes by Molecular Weight",
        "the tested step",
    ]
