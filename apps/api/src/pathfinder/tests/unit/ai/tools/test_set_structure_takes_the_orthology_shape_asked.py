"""``set_structure`` refuses a round trip when the message carries the genes to
an organism, and a one-way transform when it keeps the genes that have an
ortholog there."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_structure import set_structure
from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.orthology_request import OrthologyRequest
from pathfinder.tests._support.organism_reads import serve_organism_reads
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context
from pathfinder.tests.unit.domain.strategy._orthology import (
    SOURCE,
    kept_by_intersect,
    leg,
    seed_criteria,
    seed_node,
)

_ME49 = "Toxoplasma gondii ME49"
_CARRY = "Carry these to their syntenic orthologs in Toxoplasma gondii ME49."
_KEEP = "Keep only those with syntenic orthologs in Toxoplasma gondii ME49."


def _state(message: str) -> AgentToolState:
    state = AgentToolState()
    state.operational_spec_draft = OperationalSpec(
        goal=message,
        criteria=[
            *seed_criteria(),
            leg("c_to", _ME49, "yes"),
            leg("c_back", SOURCE, "yes"),
        ],
    )
    state.orthology_request = OrthologyRequest.read(message)
    return state


def _carried() -> StructureNode:
    return StructureNode(kind="transform", criterion_id="c_to", inputs=[seed_node()])


@pytest.mark.asyncio
async def test_a_round_trip_for_a_carry_is_refused() -> None:
    state = _state(_CARRY)

    with pytest.raises(ModelRetry) as refused:
        await set_structure(
            agent_run_context(agent_state=state), root=kept_by_intersect(seed_node())
        )

    assert refused.value.message == (
        f"The structure is refused: The message carries the genes to {_ME49}, "
        f"which asks for one transform whose result is the genes of {_ME49}. "
        f"c_back maps them back to {SOURCE}, a round trip that keeps the source "
        'genes. State {"kind": "transform", "criterionId": "<the transform>", '
        '"inputs": [<the source subtree>]} with the organism the message names, '
        "and no transform back. Nothing was recorded."
    )
    assert state.operational_spec_draft.structure is None


@pytest.mark.asyncio
async def test_one_transform_for_a_carry_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_organism_reads(monkeypatch, [SOURCE, _ME49])
    state = _state(_CARRY)

    await set_structure(agent_run_context(agent_state=state), root=_carried())

    assert state.operational_spec_draft.structure == SpecStructure(root=_carried())


@pytest.mark.asyncio
async def test_a_one_way_transform_for_a_kept_gene_is_refused() -> None:
    state = _state(_KEEP)

    with pytest.raises(ModelRetry) as refused:
        await set_structure(agent_run_context(agent_state=state), root=_carried())

    assert refused.value.message.startswith(
        f"The structure is refused: The message keeps the genes that have an "
        f"ortholog in {_ME49}, which asks for the round trip that keeps the "
        f"source genes. c_to returns the genes of {_ME49} where the source holds "
        f"genes of {SOURCE}."
    )
    assert state.operational_spec_draft.structure is None


@pytest.mark.asyncio
async def test_a_round_trip_held_before_a_carry_stands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_organism_reads(monkeypatch, [SOURCE, _ME49])
    state = _state(_CARRY)
    held = kept_by_intersect(seed_node())
    state.held_structure = SpecStructure(root=held)

    await set_structure(agent_run_context(agent_state=state), root=held)

    assert state.operational_spec_draft.structure == SpecStructure(root=held)
