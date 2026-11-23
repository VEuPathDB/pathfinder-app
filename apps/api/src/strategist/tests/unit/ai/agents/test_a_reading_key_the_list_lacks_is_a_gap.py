from __future__ import annotations

from strategist.ai.agents.frame_reading_checks import hold_the_readings_to_the_site
from strategist.ai.agents.state import AgentToolState
from strategist.ai.lead.deltas import FrameResult, PassGap
from strategist.domain.strategy.operational_spec import OperationalSpec
from strategist.domain.strategy.readings import Reading
from strategist.tests._support.held_answers import let_through
from strategist.tests.unit.ai.agents.test_a_reading_is_one_the_site_can_build import (
    _PRESENT,
    _SPACED,
    EVERY,
    _criterion,
    _question,
    validated,
)
from strategist.tests.unit.ai.tools.conftest import agent_run_context

__all__ = ["validated"]


async def test_a_key_the_list_lacks_beside_a_held_one_is_let_through_with_its_gap(
    validated: list[str],
) -> None:
    question = _question(
        Reading(label="Every one of the 61 genomes", value=EVERY),
        Reading(label="Most of them", value=_SPACED),
        requirements=["R1", "R9"],
    )
    asked = FrameResult(disposition="needs_user", open_questions=[question])
    state = AgentToolState(
        operational_spec_draft=OperationalSpec(criteria=[_criterion()]),
        stated_requirements=[_PRESENT],
    )

    _, held = await hold_the_readings_to_the_site(
        agent_run_context(agent_state=state), asked
    )

    assert let_through(held, asked).gaps == [
        PassGap(
            kind="reading_keys_unknown",
            sentence=(
                "'Present in which Plasmodium genomes?' names ['R9'], which the "
                "requirement list does not hold, so a pick of its readings replaces "
                "none of them."
            ),
        )
    ]
