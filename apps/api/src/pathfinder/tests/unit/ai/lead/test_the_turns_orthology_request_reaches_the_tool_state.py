"""The dispatch reads the orthology shape of the turn's message into the tool
state, and a carry names its organism only for a transform the tree adds."""

from __future__ import annotations

from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.orthology_request import OrthologyRequest
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_ME49 = "Toxoplasma gondii ME49"
_CARRY = f"Carry these to their syntenic orthologs in {_ME49}."


def test_the_turns_carry_reaches_the_tool_state() -> None:
    state = pipeline_state("veupathdb", user_prompt=_CARRY)

    tool_state = agent_deps_for(lead_deps(state)).agent_state

    assert tool_state.orthology_request == OrthologyRequest(
        shape="transform", target=_ME49
    )
    assert tool_state.carried_to("c_to_me49") == _ME49


def test_a_transform_the_found_tree_holds_is_carried_nowhere() -> None:
    state = pipeline_state("veupathdb", user_prompt=_CARRY)
    state.domain.spec_before_dispatch = OperationalSpec(
        criteria=[Criterion(id="c_seed", text="seed"), Criterion(id="c_to", text="to")],
        structure=SpecStructure(
            root=StructureNode(
                kind="transform",
                criterion_id="c_to",
                inputs=[StructureNode(kind="leaf", criterion_id="c_seed")],
            )
        ),
    )

    tool_state = agent_deps_for(lead_deps(state)).agent_state

    assert tool_state.carried_to("c_to") == ""
    assert tool_state.carried_to("c_to_me49") == _ME49


def test_a_kept_gene_carries_no_transform() -> None:
    state = pipeline_state(
        "veupathdb", user_prompt=f"Keep only those with syntenic orthologs in {_ME49}."
    )

    tool_state = agent_deps_for(lead_deps(state)).agent_state

    assert tool_state.orthology_request == OrthologyRequest(
        shape="round_trip", target=_ME49
    )
    assert tool_state.carried_to("c_to_me49") == ""
