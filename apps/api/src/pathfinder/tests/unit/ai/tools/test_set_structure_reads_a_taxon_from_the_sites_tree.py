"""``set_structure`` takes an INTERSECT of a search scoped to a taxon and a
search scoped to an organism the site's tree holds under that taxon."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_structure import set_structure
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    StructureNode,
)
from pathfinder.tests._support.organism_reads import (
    serve_organism_reads,
    serve_organism_trees,
    serve_universe_counts,
)
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_PK = "Plasmodium knowlesi strain H"
_TG = "Toxoplasma gondii ME49"
_TREE = {"Apicomplexa": frozenset({_PK, _TG}), "Plasmodium": frozenset({_PK})}


def _annotated(criterion_id: str, organism: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=f"genes with transporter activity in {organism}",
        search_name="GenesByGoTerm",
        organism_param="organism",
        resolved_params={
            "organism": BoundValue(
                value=MultiPickValue(values=[organism]), source="stated"
            )
        },
    )


def _both(group: str, organism: str) -> tuple[AgentToolState, StructureNode]:
    state = AgentToolState()
    state.frame_set_criterion(_annotated("c_group", group))
    state.frame_set_criterion(_annotated("c_organism", organism))
    tree = StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[
            StructureNode(kind="leaf", criterion_id="c_group"),
            StructureNode(kind="leaf", criterion_id="c_organism"),
        ],
    )
    return state, tree


@pytest.fixture
def trees_read(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    serve_organism_reads(monkeypatch, [_PK, _TG])
    serve_universe_counts(monkeypatch, {})
    return serve_organism_trees(monkeypatch, _TREE)


@pytest.mark.asyncio
async def test_a_taxon_and_an_organism_under_it_intersect(
    trees_read: list[dict[str, str]],
) -> None:
    state, tree = _both("Apicomplexa", _PK)

    await set_structure(agent_run_context(agent_state=state), root=tree)

    structure = state.operational_spec_draft.structure
    assert structure is not None
    assert structure.root == tree
    assert trees_read == [{"GenesByGoTerm": "organism"}]


@pytest.mark.asyncio
async def test_a_taxon_and_an_organism_outside_it_are_refused(
    trees_read: list[dict[str, str]],
) -> None:
    state, tree = _both("Plasmodium", _TG)

    with pytest.raises(ModelRetry) as refused:
        await set_structure(agent_run_context(agent_state=state), root=tree)

    assert refused.value.message == (
        "The structure is refused: Cannot INTERSECT steps with different organism "
        f"scopes (Plasmodium vs {_TG}). Gene IDs from different organisms never "
        "match, so this always returns 0 results. Scope every seed to one "
        f"organism: Plasmodium or {_TG}. Nothing was recorded."
    )
    assert state.operational_spec_draft.structure is None


@pytest.mark.asyncio
async def test_scopes_of_one_name_read_no_tree(
    trees_read: list[dict[str, str]],
) -> None:
    state, tree = _both(_PK, _PK)

    await set_structure(agent_run_context(agent_state=state), root=tree)

    assert trees_read == []
