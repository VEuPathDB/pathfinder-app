"""The requirement arcs play the shapes their findings name, and the app holds
each to its invariant: a compared side is no constraint, and a card of labels
over an empty combine is refused."""

from __future__ import annotations

from uuid import uuid4

import pytest
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.models.mock.requirement_arcs import COMPARED_SIDES
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from pathfinder.tests.unit.ai.models._mock_turns import args_of, names, play

SITES = ("plasmodb", "vectorbase")


@pytest.mark.parametrize("site_id", SITES)
def test_a_compared_side_the_model_writes_is_no_constraint(site_id: str) -> None:
    calls = play("lead", site_id, "Which finds more? [[arc:comparison-sides]]")

    [classified] = args_of(calls, "classify_user_intent")
    intent = UserIntent.model_validate(classified["intent"])
    assert names(calls) == ["classify_user_intent", "final_result"]
    assert intent.differential_sides == COMPARED_SIDES
    assert [(c.kind, c.requested_value) for c in intent.explicit_constraints] == [
        (ConstraintKind.ORGANISM, SiteValues.for_site(site_id).organism)
    ]


def _empty_combine(site_id: str) -> LeadDeps:
    proxy = Criterion(
        id="c_oocyst_expression_proxy",
        text="expressed in oocysts",
        search_name="GenesByRNASeqPercentile",
        resolved_params={
            "min_expression_percentile": BoundValue(
                value=StringValue(value="80"), source="chosen"
            )
        },
        param_display_names={
            "min_expression_percentile": "Minimum expression percentile"
        },
        result_count=783,
    )
    return lead_deps(
        pipeline_state(
            site_id,
            user_prompt="an answer to the card",
            user_message_id=uuid4(),
            domain=StrategyDomainState(
                operational_spec=OperationalSpec(criteria=[proxy])
            ),
        )
    )
