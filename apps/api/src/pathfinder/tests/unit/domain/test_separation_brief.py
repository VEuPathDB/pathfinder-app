"""The Lead reads a separation run as counts and sentences, never as gene ids."""

from __future__ import annotations

import re

from pathfinder.domain.separation_brief import brief_of
from pathfinder.services.separation.offer import separation_report
from pathfinder.tests._support.separation import (
    SIGNAL_PEPTIDE,
    TASK_ID,
    recorded_separation,
)

_GENE_ID = re.compile(r"PF3D7_\d{7}")


def _brief_json() -> str:
    report = separation_report(recorded_separation(SIGNAL_PEPTIDE), task_id=TASK_ID)
    return brief_of(report).model_dump_json(by_alias=True)


def test_the_brief_holds_the_counts_the_reply_is_written_from() -> None:
    report = separation_report(recorded_separation(SIGNAL_PEPTIDE), task_id=TASK_ID)

    brief = brief_of(report).model_dump(by_alias=True, mode="json")

    assert brief == {
        "taskId": str(TASK_ID),
        "mode": "exact",
        "summary": (
            "no strategy separates the sets; closest: 61 of 80 positives, "
            "2 of 40 negatives, 1,132 genes, 3 searches; 384 of 400 requests"
        ),
        "offer": {
            "question": (
                "Build the closest strategy found: 3 searches returning 61 of 80 "
                "positives and 2 of 40 negatives in 1,132 genes?"
            ),
            "separates": False,
            "positivesReturned": 61,
            "positiveControls": 80,
            "negativesReturned": 2,
            "negativeControls": 40,
            "resultSize": 1132,
            "criteria": [
                {
                    "displayName": "GO Term",
                    "positivesReturned": 42,
                    "negativesReturned": 0,
                },
                {
                    "displayName": (
                        "Gene Lists from PlasmoAP motif for protein export to the "
                        "apicoplast."
                    ),
                    "positivesReturned": 31,
                    "negativesReturned": 2,
                },
                {
                    "displayName": "GO Term",
                    "positivesReturned": 38,
                    "negativesReturned": 0,
                },
            ],
        },
        "measuredCount": 20,
        "informativeCount": 17,
        "skippedByReason": {
            "budget": 1,
            "needs_an_analysis": 1,
            "transform": 1,
            "unbound_required": 5,
            "wdk_refused": 7,
        },
        "unresolvedPositiveCount": 0,
        "unresolvedNegativeCount": 0,
        "chargedRequests": 384,
        "budget": 400,
    }


def test_the_brief_names_no_gene_and_stays_under_two_kilobytes() -> None:
    assert _GENE_ID.findall(_brief_json()) == []
    assert len(_brief_json()) < 2048


def test_a_run_with_no_offer_is_briefed_with_its_sentence() -> None:
    report = separation_report(recorded_separation(SIGNAL_PEPTIDE), task_id=TASK_ID)
    bare = report.model_copy(
        update={
            "offer": None,
            "shortfall": ["No measured criterion recovers any positive."],
        }
    )

    brief = brief_of(bare)

    assert (brief.offer, brief.summary) == (
        None,
        "no strategy assembled; No measured criterion recovers any positive.",
    )
