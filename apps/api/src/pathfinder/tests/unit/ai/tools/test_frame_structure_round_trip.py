"""``set_structure`` takes a copy of a subtree the tree states, and refuses an
orthology round trip that would not keep the source genes."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_structure import (
    SetStructureResult,
    set_structure,
)
from pathfinder.domain.strategy.operational_spec import StructureNode
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context
from pathfinder.tests.unit.domain.strategy._orthology import (
    kept_by_intersect,
    round_trip_spec,
    seed_node,
    trip,
)


def _drafted() -> AgentToolState:
    state = AgentToolState()
    state.operational_spec_draft = round_trip_spec().model_copy(
        update={"structure": None}
    )
    return state


@pytest.mark.asyncio
async def test_the_kept_round_trip_is_set_with_its_copy() -> None:
    state = _drafted()
    root = kept_by_intersect(seed_node())

    result = returned(
        await set_structure(agent_run_context(agent_state=state), root=root),
        SetStructureResult,
    )

    structure = state.operational_spec_draft.structure
    assert structure is not None
    assert structure.root == root
    assert result.criteria_combined == 4


@pytest.mark.asyncio
async def test_a_round_trip_without_the_intersect_is_refused() -> None:
    state = _drafted()

    with pytest.raises(ModelRetry) as exc:
        await set_structure(
            agent_run_context(agent_state=state), root=trip(seed_node())
        )

    assert "c_back (Transform by Orthology)" in str(exc.value)
    assert '{"kind": "copy", "inputs": [<the source subtree>]}' in str(exc.value)
    assert state.operational_spec_draft.structure is None


@pytest.mark.asyncio
async def test_a_criterion_named_twice_is_refused_toward_a_copy() -> None:
    state = _drafted()
    root = StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[seed_node(), trip(seed_node())],
    )

    with pytest.raises(ModelRetry) as exc:
        await set_structure(agent_run_context(agent_state=state), root=root)

    assert "c_signal appears twice in the tree" in str(exc.value)
    assert state.operational_spec_draft.structure is None
