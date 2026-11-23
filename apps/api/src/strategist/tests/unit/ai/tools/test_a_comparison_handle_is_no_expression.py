"""A computed comparison's handle bound as a phyletic expression is sent back
to be passed as computed_groups, and never reaches the site."""

from __future__ import annotations

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone._expression_handles import (
    with_stored_expressions,
)
from strategist.ai.tools.standalone._frame_proposals import CriterionCall


def test_a_groups_handle_as_an_expression_is_sent_back() -> None:
    call = CriterionCall(
        criterion_id="c_more",
        search_name="GroupsByPhyleticPattern",
        text="more proteins in Toxoplasma",
        params={"phyletic_expression": " groups:7379dc1b9493 "},
    )

    kept, refused = with_stored_expressions(AgentToolState(), call)

    assert kept == call
    assert refused.text() == (
        "phyletic_expression names groups:7379dc1b9493, the handle of a computed "
        "comparison, which no expression states. Pass it to set_criterion as "
        "computed_groups instead."
    )
