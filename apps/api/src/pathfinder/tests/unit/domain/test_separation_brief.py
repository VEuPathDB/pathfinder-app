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
    report = separation_report(
        recorded_separation(SIGNAL_PEPTIDE), task_id=TASK_ID, sheets={}
    )
    return brief_of(report).model_dump_json(by_alias=True)


def test_the_brief_holds_the_counts_the_reply_is_written_from() -> None:
    report = separation_report(
        recorded_separation(SIGNAL_PEPTIDE), task_id=TASK_ID, sheets={}
    )

    brief = brief_of(report).model_dump(by_alias=True, mode="json")

    assert brief == {
        "taskId": str(TASK_ID),
        "mode": "exact",
        "summary": (
            "no strategy separates the sets; closest: 50 of 80 positives, "
            "0 of 40 negatives, 800 genes, 3 searches; 379 of 400 requests"
        ),
        "offer": {
            "question": (
                "Build the closest strategy found: 3 searches returning 50 of 80 "
                "positives and 0 of 40 negatives in 800 genes?"
            ),
            "separates": False,
            "positivesReturned": 50,
            "positiveControls": 80,
            "negativesReturned": 0,
            "negativeControls": 40,
            "resultSize": 800,
            "criteria": [
                {
                    "displayName": "GO Term",
                    "positivesReturned": 42,
                    "negativesReturned": 0,
                },
                {
                    "displayName": "GO Term",
                    "positivesReturned": 38,
                    "negativesReturned": 0,
                },
                {
                    "displayName": (
                        "Gene Lists from Pexel motif analysis of protein export to "
                        "the erythrocyte membrane."
                    ),
                    "positivesReturned": 33,
                    "negativesReturned": 0,
                },
            ],
        },
        "measuredCount": 23,
        "informativeCount": 14,
        "skippedByReason": {
            "budget": 2,
            "unbound_required": 4,
            "wdk_refused": 2,
        },
        "unresolvedPositiveCount": 0,
        "unresolvedNegativeCount": 0,
        "chargedRequests": 379,
        "budget": 400,
    }


def test_the_brief_names_no_gene_and_stays_under_two_kilobytes() -> None:
    assert _GENE_ID.findall(_brief_json()) == []
    assert len(_brief_json()) < 2048


def test_a_run_with_no_offer_is_briefed_with_its_sentence() -> None:
    report = separation_report(
        recorded_separation(SIGNAL_PEPTIDE), task_id=TASK_ID, sheets={}
    )
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
