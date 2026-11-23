"""The requirement arcs play the shapes their findings name: a compared side the
reading writes is a side, never a constraint."""

from __future__ import annotations

import pytest

from strategist.domain.strategy.constraints import ConstraintKind
from strategist.tests.unit.ai.lead.conftest import pipeline_state
from strategist.tests.unit.scripted.models._mock_turns import names, play
from strategist_scripted.models.reading import scripted_intent
from strategist_scripted.models.requirement_arcs import COMPARED_SIDES
from strategist_scripted.models.site_values import SiteValues

SITES = ("plasmodb", "vectorbase")


@pytest.mark.parametrize("site_id", SITES)
def test_a_compared_side_the_reading_writes_is_a_side(site_id: str) -> None:
    text = "Which finds more? [[arc:comparison-sides]]"
    calls = play("lead", site_id, text)

    intent = scripted_intent(pipeline_state(site_id, user_prompt=text), text)
    assert names(calls) == ["final_result"]
    assert intent.differential_sides == COMPARED_SIDES
    assert [(c.kind, c.requested_value) for c in intent.explicit_constraints] == [
        (ConstraintKind.ORGANISM, SiteValues.for_site(site_id).organism)
    ]
