"""No arc carries the organism, the genus or a control gene of the other site
into a turn, in either direction."""

from __future__ import annotations

import pytest

from pathfinder.ai.models.mock.registry import ARCS
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.tests.unit.ai.models._mock_pins import edit_order
from pathfinder.tests.unit.ai.models._mock_turns import (
    as_json,
    names,
    play,
    verify_order,
)

_FRAME_ORDER = "Frame work order: mock frame"
_PAIRS = [("plasmodb", "vectorbase"), ("vectorbase", "plasmodb")]


def _played(arc: str, site_id: str) -> str:
    text = f"Do it [[arc:{arc}]]"
    loop = 3 if arc == "frame-loop" else 40
    calls = [
        *play("lead", site_id, text),
        *play("frame", site_id, text, work_order=_FRAME_ORDER, limit=loop),
        *play("frame", site_id, text, work_order=edit_order(site_id), limit=loop),
        *play("verification", site_id, text, work_order=verify_order(12)),
        *play("execution", site_id, text),
    ]
    assert names(calls)[-1] == "final_result"
    return as_json(calls)


def _values_of(site_id: str) -> list[str]:
    values = SiteValues.for_site(site_id)
    genus = values.organism.split(" ", maxsplit=1)[0]
    return [
        values.organism,
        genus,
        *values.controls.positive_ids,
        *values.controls.negative_ids,
    ]


@pytest.mark.parametrize(("site_id", "other"), _PAIRS)
@pytest.mark.parametrize("arc", sorted(ARCS))
def test_a_turn_names_no_value_of_the_other_site(
    arc: str, site_id: str, other: str
) -> None:
    held = _played(arc, site_id)

    assert [value for value in _values_of(other) if value in held] == []
