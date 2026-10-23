from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_structure import (
    SetStructureResult,
    set_structure,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    SavedStrategyRef,
    StructureNode,
)
from pathfinder.tests._support.orthomcl_record_classes import (
    serve_orthomcl_record_classes,
)
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


@pytest.fixture(autouse=True)
def _orthomcl(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_orthomcl_record_classes(monkeypatch)


def _state() -> AgentToolState:
    state = AgentToolState()
    for criterion in (
        Criterion(id="c_tb927_10_10390", text="the protein", search_name="ByIdList"),
        Criterion(
            id="c_mammal_presence",
            text="groups with a mammal protein",
            search_name="GroupsByPhyleticPattern",
        ),
        Criterion(
            id="c_groups",
            text="the protein's ortholog group",
            search_name="GroupsFromSequences",
            role="transform",
        ),
    ):
        state.frame_set_criterion(criterion)
    return state


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _intersect(left: StructureNode) -> StructureNode:
    return StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[left, _leaf("c_mammal_presence")],
    )


@pytest.mark.asyncio
async def test_a_protein_leaf_intersected_with_a_group_leaf_is_refused() -> None:
    state = _state()

    with pytest.raises(ModelRetry) as refused:
        await set_structure(
            agent_run_context(site_id="orthomcl", agent_state=state),
            root=_intersect(_leaf("c_tb927_10_10390")),
        )

    assert state.operational_spec_draft.structure is None
    assert str(refused.value) == (
        "The structure is refused: The INTERSECT of c_tb927_10_10390 (Proteins) "
        "and c_mammal_presence (Ortholog Groups) joins two record types. WDK "
        "combines only steps of one record type, so the site refuses this combine. "
        "Transform Proteins to Groups (GroupsFromSequences) maps Proteins to "
        "Ortholog Groups: put it over c_tb927_10_10390. Transform Groups to "
        "Proteins (FromGroups) maps Ortholog Groups to Proteins: put it over "
        "c_mammal_presence. Nothing was recorded."
    )


@pytest.mark.asyncio
async def test_the_proteins_groups_intersected_with_a_group_leaf_are_set() -> None:
    state = _state()
    groups = StructureNode(
        kind="transform", criterion_id="c_groups", inputs=[_leaf("c_tb927_10_10390")]
    )

    result = await set_structure(
        agent_run_context(site_id="orthomcl", agent_state=state),
        root=_intersect(groups),
    )

    assert returned(result, SetStructureResult).criteria_combined == 3


@pytest.mark.asyncio
async def test_a_saved_protein_strategy_intersected_with_a_group_leaf_is_refused() -> (
    None
):
    state = _state()
    state.frame_set_criterion(
        Criterion(
            id="c_saved_proteins",
            text="my saved proteins",
            record_class="sequence",
            saved_strategy_ref=SavedStrategyRef(
                conversation_id="9bd3a584-0000-4000-8000-000000000001",
                name="Trypanothione reductase proteins",
                wdk_strategy_id=227284890,
                step_count=1,
                subtree=StrategyStepNode(id="step_saved", search_name="ByIdList"),
            ),
        )
    )

    with pytest.raises(ModelRetry) as refused:
        await set_structure(
            agent_run_context(site_id="orthomcl", agent_state=state),
            root=_intersect(_leaf("c_saved_proteins")),
        )

    assert state.operational_spec_draft.structure is None
    assert str(refused.value).startswith(
        "The structure is refused: The INTERSECT of c_saved_proteins (Proteins) "
        "and c_mammal_presence (Ortholog Groups) joins two record types."
    )
