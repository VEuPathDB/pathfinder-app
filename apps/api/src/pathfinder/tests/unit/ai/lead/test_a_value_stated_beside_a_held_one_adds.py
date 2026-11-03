from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.held_intent import hold_the_intent
from pathfinder.ai.lead.message_intent import intent_of
from pathfinder.domain.message_reading import (
    MessageReading,
    StatedOrganism,
    StatedRequest,
)
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_HELD = Constraint(
    kind=ConstraintKind.ORGANISM,
    requested_value="Plasmodium falciparum 3D7",
    label="Plasmodium falciparum 3D7",
    source=ConstraintSource.USER_EXPLICIT,
    quote="Plasmodium falciparum 3D7",
)
_MESSAGE = "Also include Plasmodium vivax P01."


def _reading(beside: str) -> StatedRequest:
    return StatedRequest(
        requirements=[
            StatedOrganism(
                quote="Plasmodium vivax P01",
                kind="organism",
                value="Plasmodium vivax P01",
                organism="Plasmodium vivax P01",
                beside=beside,
            )
        ]
    )


async def _held_after(beside: str) -> list[str]:
    state = pipeline_state(
        user_prompt=_MESSAGE,
        user_message_id=uuid4(),
        domain=StrategyDomainState(requirements=[_HELD]),
    )
    reading = MessageReading(effect="add", wants="nothing", read_by="script")

    await hold_the_intent(
        lead_deps(state), intent_of(reading, _reading(beside)), _MESSAGE
    )

    return [c.requested_value for c in state.domain.requirements]


@pytest.mark.usefixtures("recorded_site_organisms")
async def test_a_value_stated_beside_the_held_one_stands_beside_it() -> None:
    assert await _held_after("R1") == [
        "Plasmodium falciparum 3D7",
        "Plasmodium vivax P01",
    ]


@pytest.mark.usefixtures("recorded_site_organisms")
async def test_a_value_beside_a_number_the_thread_does_not_hold_replaces() -> None:
    assert await _held_after("R7") == ["Plasmodium vivax P01"]
