"""A set saved on OrthoMCL lists on PlasmoDB with the site it was saved on and
the count of its genes PlasmoDB holds."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest

from pathfinder.ai.tools.standalone import gene_sets
from pathfinder.ai.tools.standalone.gene_set_models import (
    GeneSetCreatedResponse,
    GeneSetListResponse,
)
from pathfinder.domain.gene_homes import GeneHome
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.tests._support.gene_set_store import keep_saved
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_PROTEINS = GeneSet(
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


async def test_a_set_from_orthomcl_lists_its_site_and_the_genes_here(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _listed(*, site_id: str, user_id: UUID | None) -> list[GeneSet]:
        del site_id, user_id
        return [_PROTEINS]

    monkeypatch.setattr(gene_sets, "list_stored_gene_sets", _listed)

    listed = returned(
        await gene_sets.list_gene_sets(agent_run_context()), GeneSetListResponse
    )

    assert [
        (s.name, s.saved_on, s.gene_count, s.genes_on_this_site)
        for s in listed.gene_sets
    ] == [("3D7 strain gaps", "orthomcl", 3, 2)]


async def test_a_saved_set_says_where_a_conversation_can_start_from_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gene_sets, "store_gene_set", keep_saved([]))

    saved = returned(
        await gene_sets.save_gene_set(
            agent_run_context(), name="kinases", gene_ids=["PF3D7_0103400"]
        ),
        GeneSetCreatedResponse,
    )

    assert saved.message == (
        "Gene set 'kinases' with 1 genes has been saved in PathFinder. A "
        "conversation on PlasmoDB, VEuPathDB or OrthoMCL can start from it; it "
        "reaches the VEuPathDB workspace only when it is published. It holds gene "
        "IDs only: this conversation has no pushed strategy step behind them."
    )


@pytest.mark.parametrize(
    ("site_id", "noun"), [("plasmodb", "gene"), ("orthomcl", "protein")]
)
async def test_a_set_of_no_record_type_counts_the_sites_genes(
    monkeypatch: pytest.MonkeyPatch, site_id: str, noun: str
) -> None:
    async def _listed(*, site_id: str, user_id: UUID | None) -> list[GeneSet]:
        del user_id
        return [replace(_PROTEINS, site_id=site_id)]

    monkeypatch.setattr(gene_sets, "list_stored_gene_sets", _listed)

    listed = returned(
        await gene_sets.list_gene_sets(agent_run_context(site_id=site_id)),
        GeneSetListResponse,
    )

    assert [row.record_noun for row in listed.gene_sets] == [noun]
