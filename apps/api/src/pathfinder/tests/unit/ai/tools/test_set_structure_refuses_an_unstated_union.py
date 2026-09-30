"""``set_structure`` refuses a UNION of the strategy's own step and a new arm
that no stated OR joins, and names the comparison that answers instead."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_structure import set_structure
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import Criterion, StructureNode
from pathfinder.tests.unit.ai.lead.conftest import session_with_one_step
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_HELD = "step_dd5b456c"
_ADDED = "c_treu927_rna_binding_domains"


def _state(*requirements: Constraint) -> AgentToolState:
    state = AgentToolState()
    state.frame_set_criterion(
        Criterion(
            id=_HELD,
            text="DAL972 genes with an RNA-binding domain",
            search_name="GenesByInterproDomain",
        )
    )
    state.frame_set_criterion(
        Criterion(
            id=_ADDED,
            text="TREU927 genes with the same domains",
            search_name="GenesByInterproDomain",
        )
    )
    state.combination_requirements = list(requirements)
    return state


def _union() -> StructureNode:
    return StructureNode(
        kind="combine",
        operator=CombineOp.UNION,
        inputs=[
            StructureNode(kind="leaf", criterion_id=_HELD),
            StructureNode(kind="leaf", criterion_id=_ADDED),
        ],
    )


@pytest.mark.asyncio
async def test_a_union_of_the_held_step_and_the_comparison_arm_is_refused() -> None:
    state = _state()
    ctx = agent_run_context(
        site_id="tritrypdb",
        agent_state=state,
        strategy_session=session_with_one_step("tritrypdb", step_id=_HELD),
    )

    with pytest.raises(ModelRetry) as refused:
        await set_structure(ctx, root=_union())

    message = refused.value.message
    assert message.startswith(
        f"The structure is refused: a UNION joins {_HELD}, which the strategy "
        f"holds, to {_ADDED}, which this turn adds"
    )
    assert "compare_search_variants" in message
    assert "end needs_user with a Drop/Keep question" in message
    assert state.operational_spec_draft.structure is None


@pytest.mark.asyncio
async def test_a_stated_or_over_both_strains_lets_the_union_stand() -> None:
    stated = Constraint(
        kind=ConstraintKind.COMBINATION,
        requested_value="DAL972 genes OR TREU927 genes",
        label="how the requirements combine",
        source=ConstraintSource.USER_EXPLICIT,
    )
    state = _state(stated)
    ctx = agent_run_context(
        site_id="tritrypdb",
        agent_state=state,
        strategy_session=session_with_one_step("tritrypdb", step_id=_HELD),
    )

    await set_structure(ctx, root=_union())

    assert state.operational_spec_draft.structure is not None
    assert state.operational_spec_draft.structure.root == _union()
