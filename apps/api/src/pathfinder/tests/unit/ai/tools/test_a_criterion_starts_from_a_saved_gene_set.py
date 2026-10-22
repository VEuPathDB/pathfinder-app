"""A criterion starts from a saved gene set, on this site or another: the set's
genes here become an id-list dataset that the site's id search reads."""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic_ai import ModelRetry, RunContext
from veupathdb.domain.parameters import InputDatasetValue
from veupathdb.wdk import WDKDatasetConfigIdList

from pathfinder.ai.agents.frame import _FRAME_INSTRUCTIONS
from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import _frame_gene_set
from pathfinder.ai.tools.standalone._frame_result import (
    GeneSetBinding,
    SetCriterionResult,
)
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.ai.tools.standalone.frame_structure import set_structure
from pathfinder.domain.gene_homes import GeneHome
from pathfinder.domain.strategy.operational_spec import BoundValue, StructureNode
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.strategies import dataset_sources
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._orthomcl_site import (
    group_strategy_ctx,
    serve_orthomcl,
)
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_STRAIN_GAPS = GeneSet(
    id="gs-ortho",
    name="3D7 strain gaps",
    site_id="orthomcl",
    gene_ids=["PF3D7_0103400.1-p1", "PF3D7_0110100.1-p1", "TGME49_200250-t26_1-p1"],
    source="strategy",
    homes={
        "PF3D7_0103400.1-p1": GeneHome(gene_id="PF3D7_0103400", site_id="plasmodb"),
        "PF3D7_0110100.1-p1": GeneHome(gene_id="PF3D7_0110100", site_id="plasmodb"),
        "TGME49_200250-t26_1-p1": GeneHome(gene_id="TGME49_200250", site_id="toxodb"),
    },
)


class _Site:
    def __init__(self) -> None:
        self.datasets: list[list[str]] = []

    async def create_dataset(self, config: WDKDatasetConfigIdList) -> int:
        self.datasets.append(config.source_content.ids)
        return 9001


def _serve(monkeypatch: pytest.MonkeyPatch) -> _Site:
    site = _Site()

    async def _listed(*, site_id: str, user_id: UUID | None) -> list[GeneSet]:
        del site_id, user_id
        return [_STRAIN_GAPS]

    monkeypatch.setattr(_frame_gene_set, "list_stored_gene_sets", _listed)
    monkeypatch.setattr(dataset_sources, "get_strategy_api", lambda _site_id: site)
    return site


def _ctx(state: AgentToolState) -> RunContext[AgentDeps]:
    return agent_run_context(agent_state=state, db_session_factory=no_database)


async def test_a_set_from_orthomcl_binds_its_plasmodb_genes_to_the_id_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch)
    state = AgentToolState()

    result = returned(
        await set_criterion(
            _ctx(state),
            criterion_id="c_strain_gaps",
            text="the genes in my set 3D7 strain gaps",
            role="seed",
            gene_set="3D7 strain gaps",
        ),
        SetCriterionResult,
    )

    [criterion] = state.operational_spec_draft.criteria
    assert (criterion.search_name, criterion.search_display_name, criterion.role) == (
        "GeneByLocusTag",
        "Gene set: 3D7 strain gaps",
        "seed",
    )
    assert criterion.resolved_params == {
        "ds_gene_ids": BoundValue(
            value=InputDatasetValue(dataset_id="9001"),
            source="chosen",
            basis="the saved gene set 3D7 strain gaps",
            label="2 of the 3 genes of 3D7 strain gaps, saved on OrthoMCL",
        )
    }
    assert criterion.param_display_names == {"ds_gene_ids": "Genes"}
    assert site.datasets == [["PF3D7_0103400", "PF3D7_0110100"]]
    assert result.gene_set == GeneSetBinding(
        id="gs-ortho",
        name="3D7 strain gaps",
        saved_on="orthomcl",
        gene_count=3,
        genes_here=2,
    )


async def test_the_set_is_named_by_its_id_too(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch)
    state = AgentToolState()

    await set_criterion(
        _ctx(state),
        criterion_id="c_strain_gaps",
        text="that set",
        role="seed",
        gene_set="gs-ortho",
    )

    assert [c.search_display_name for c in state.operational_spec_draft.criteria] == [
        "Gene set: 3D7 strain gaps"
    ]


async def test_a_name_no_set_holds_retries_with_the_sets_this_site_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)
    state = AgentToolState()

    with pytest.raises(ModelRetry, match="'3D7 strain gaps'"):
        await set_criterion(
            _ctx(state),
            criterion_id="c_x",
            text="my kinases",
            role="seed",
            gene_set="kinases",
        )
    assert state.operational_spec_draft.criteria == []


async def test_a_set_is_an_input_and_maps_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)

    with pytest.raises(ModelRetry, match='role="seed"'):
        await set_criterion(
            _ctx(AgentToolState()),
            criterion_id="c_x",
            text="map my set",
            role="transform",
            gene_set="gs-ortho",
        )


def test_frame_starts_from_a_set_the_listing_names() -> None:
    told = " ".join(_FRAME_INSTRUCTIONS.split())

    assert 'gene_set="<name from the listing>"' in told
    assert "a set saved on OrthoMCL or the portal starts from those genes alone" in told


_PROTEINS = GeneSet(
    id="gs-proteins",
    name="3D7 proteins",
    site_id="orthomcl",
    gene_ids=["PF3D7_0103400.1-p1", "PF3D7_0110100.1-p1"],
    source="strategy",
)


async def test_a_protein_set_at_the_root_frames_the_spec_on_the_protein_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_orthomcl(monkeypatch)

    async def _listed(*, site_id: str, user_id: UUID | None) -> list[GeneSet]:
        del site_id, user_id
        return [_PROTEINS]

    monkeypatch.setattr(_frame_gene_set, "list_stored_gene_sets", _listed)
    state = AgentToolState()
    ctx = group_strategy_ctx(state)

    await set_criterion(
        ctx,
        criterion_id="c_proteins",
        text="the proteins in my set 3D7 proteins",
        role="seed",
        gene_set="3D7 proteins",
    )
    await set_structure(ctx, root=StructureNode(kind="leaf", criterion_id="c_proteins"))

    draft = state.operational_spec_draft
    assert [(c.search_name, c.record_class) for c in draft.criteria] == [
        ("ByIdList", "sequence")
    ]
    assert draft.record_type == "sequence"
