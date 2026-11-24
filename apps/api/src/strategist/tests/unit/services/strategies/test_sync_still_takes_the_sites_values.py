from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue

from strategist.services.strategies.site_changes import (
    SiteEdits,
    take_what_the_site_holds,
)
from strategist.tests.unit.ai.lead._d3_site import (
    STEP,
    graph,
    site_step,
    strategy,
    sync_state,
    the_recorded_site,
)

_MOVED = "%hsap:Y%padl:Y%"


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> None:
    the_recorded_site(monkeypatch)


async def test_a_value_the_site_moved_is_taken_onto_the_step() -> None:
    held = graph()

    edits = await take_what_the_site_holds(
        graph=held,
        sync_state=sync_state(),
        site_id="plasmodb",
        live=strategy(site_step(profile_pattern=_MOVED)),
    )

    assert edits == SiteEdits(valued=[STEP])
    assert held.steps[STEP].parameters["profile_pattern"] == StringValue(value=_MOVED)
