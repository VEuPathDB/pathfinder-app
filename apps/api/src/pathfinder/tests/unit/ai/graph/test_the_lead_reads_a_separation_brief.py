"""A finished separation answers the Lead with its brief, and the thread's card
with the whole report."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from pathfinder.ai.graph._lead_turn import resolve_turn_resumption
from pathfinder.domain.separation import SeparationReport
from pathfinder.domain.separation_brief import brief_of
from pathfinder.services.separation.offer import separation_report
from pathfinder.tests._support.separation import (
    SEPARATION_CALL,
    SIGNAL_PEPTIDE,
    TASK_ID,
    lead_answered_by_a_separation,
    recorded_separation,
)

_GENE_ID = re.compile(r"PF3D7_\d{7}")


class _Answered(BaseModel):
    """What the resumed call returns to the Lead and carries to the thread."""

    model_config = ConfigDict(from_attributes=True, arbitrary_types_allowed=True)

    return_value: dict[str, object]
    metadata: list[DataChunk]


async def _answered() -> _Answered:
    deps = lead_answered_by_a_separation(recorded_separation(SIGNAL_PEPTIDE))
    resumed = await resolve_turn_resumption(state=deps.state, deps=deps)
    assert resumed.results is not None
    return _Answered.model_validate(resumed.results.calls[SEPARATION_CALL])


async def test_the_lead_reads_the_brief_of_the_run() -> None:
    expected = brief_of(
        separation_report(recorded_separation(SIGNAL_PEPTIDE), task_id=TASK_ID)
    )

    answered = await _answered()

    assert answered.return_value == {
        "status": "success",
        "result": expected.model_dump(by_alias=True, mode="json"),
    }
    assert _GENE_ID.findall(str(answered.return_value)) == []


async def test_the_card_still_carries_every_control_of_the_run() -> None:
    answered = await _answered()

    (part,) = [c for c in answered.metadata if c.type == "data-separation-result"]
    report = SeparationReport.model_validate(part.data)

    assert report.offer is not None
    positive = report.offer.positive
    assert (len(positive.returned), len(positive.not_returned)) == (61, 19)
