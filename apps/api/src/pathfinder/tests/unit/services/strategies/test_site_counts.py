"""One read of the strategy gives the count each step holds on the site now."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb.wdk import WDKStrategyDetails

from pathfinder.services.strategies import site_counts
from pathfinder.services.strategies.site_counts import SiteCounts, read_step_counts

_DETAILS: dict[str, Any] = {
    "strategyId": 300125410,
    "name": "Kinases with a signal peptide",
    "rootStepId": 440299575,
    "recordClassName": "transcript",
    "stepTree": {
        "stepId": 440299575,
        "primaryInput": {"stepId": 440299573},
        "secondaryInput": {"stepId": 440299574},
    },
    "steps": {
        "440299573": {
            "id": 440299573,
            "searchName": "GenesByText",
            "searchConfig": {"parameters": {"text_expression": "kinase"}},
            "estimatedSize": 212,
        },
        "440299574": {
            "id": 440299574,
            "searchName": "GenesWithSignalPeptide",
            "searchConfig": {"parameters": {}},
            "estimatedSize": 1143,
        },
        "440299575": {
            "id": 440299575,
            "searchName": (
                "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"
            ),
            "searchConfig": {"parameters": {"bq_operator": "INTERSECT"}},
            "estimatedSize": -1,
        },
    },
}


class _Api:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.read: list[int] = []

    async def get_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> WDKStrategyDetails:
        del user_id
        self.read.append(strategy_id)
        if self.error is not None:
            raise self.error
        return WDKStrategyDetails.model_validate(_DETAILS)


async def test_each_step_reads_the_size_the_site_holds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _Api()
    monkeypatch.setattr(site_counts, "get_strategy_api", lambda _site: api)

    counts = await read_step_counts("plasmodb", 300125410)

    assert api.read == [300125410]
    assert counts == SiteCounts(
        root_step_id=440299575,
        counts={440299573: 212, 440299574: 1143, 440299575: None},
    )


async def test_a_site_that_does_not_answer_gives_no_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    refused = VEuPathDBError(VEuPathDBErrorCode.WDK_ERROR, "service unavailable")
    api = _Api(refused)
    monkeypatch.setattr(site_counts, "get_strategy_api", lambda _site: api)

    counts = await read_step_counts("plasmodb", 300125410)

    assert (counts, api.read) == (None, [300125410])
