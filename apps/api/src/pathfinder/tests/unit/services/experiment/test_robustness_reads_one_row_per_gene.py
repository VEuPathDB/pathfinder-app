"""The robustness phase reads the result ids of a step one row per gene."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from veupathdb.domain import WDKRecordIdPart
from veupathdb.wdk import WDKAnswer, WDKAnswerMeta, WDKFilterValue, WDKRecordInstance

from pathfinder.services.experiment.service.phases import validate


class _Answers:
    """Answers a step with one gene and records the view of each read."""

    def __init__(self) -> None:
        self.views: list[list[WDKFilterValue] | None] = []

    async def get_step_answer(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
    ) -> WDKAnswer:
        del step_id, attributes, pagination
        self.views.append(None if view_filters is None else list(view_filters))
        return WDKAnswer(
            meta=WDKAnswerMeta(),
            records=[
                WDKRecordInstance(
                    id=[WDKRecordIdPart(name="source_id", value="PF3D7_0100100")]
                )
            ],
        )


def _install(monkeypatch: pytest.MonkeyPatch) -> _Answers:
    api = _Answers()
    monkeypatch.setattr(validate, "get_strategy_api", lambda _site_id: api)
    return api


@pytest.mark.asyncio
async def test_a_transcript_step_is_read_with_the_representative_transcript(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _install(monkeypatch)

    ids = await validate._fetch_result_ids("plasmodb", 41, "transcript")

    assert ids == ["PF3D7_0100100"]
    assert api.views == [
        [WDKFilterValue(name="representativeTranscriptOnly", value={})]
    ]


@pytest.mark.asyncio
async def test_a_gene_step_is_read_with_no_view_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _install(monkeypatch)

    await validate._fetch_result_ids("plasmodb", 41, "gene")

    assert api.views == [None]
