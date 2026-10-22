"""A listing of saved gene sets puts one card on the thread: each set with the
site it was saved on and the count of its genes the viewing site holds."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from pathfinder.ai.stream_part_payloads import ListedGeneSet, ListedGeneSets
from pathfinder.ai.tools.standalone import gene_sets
from pathfinder.ai.tools.standalone.gene_set_models import GeneSetListResponse
from pathfinder.domain.gene_homes import GeneHome
from pathfinder.services.gene_sets.types import GeneSet, ResultAboveTheCap
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_THIS = uuid4()
_OUTGROWN = ResultAboveTheCap(count=309_068, cap=10_000)

_PROTEINS = GeneSet(
    id="gs-ortho",
    name="3D7 strain gaps",
    site_id="orthomcl",
    gene_ids=["PF3D7_0103400.1-p1", "PF3D7_0110100.1-p1", "TGME49_200250-t26_1-p1"],
    source="strategy",
    record_type="sequence",
    out_of_date=_OUTGROWN,
    homes={
        "PF3D7_0103400.1-p1": GeneHome(gene_id="PF3D7_0103400", site_id="plasmodb"),
        "PF3D7_0110100.1-p1": GeneHome(gene_id="PF3D7_0110100", site_id="plasmodb"),
        "TGME49_200250-t26_1-p1": GeneHome(gene_id="TGME49_200250", site_id="toxodb"),
    },
)

_KINASES = GeneSet(
    id="gs-here",
    name="Gametocyte kinases",
    site_id="plasmodb",
    gene_ids=["PF3D7_0304600", "PF3D7_1133400"],
    source="paste",
    conversation_id=_THIS,
)


async def test_the_listing_sends_a_card_of_every_set_and_its_genes_here(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _listed(*, site_id: str, user_id: UUID | None) -> list[GeneSet]:
        del site_id, user_id
        return [_PROTEINS, _KINASES]

    monkeypatch.setattr(gene_sets, "list_stored_gene_sets", _listed)
    ctx = agent_run_context(site_id="plasmodb")
    ctx.deps.conversation_id = _THIS

    result = await gene_sets.list_gene_sets(ctx)

    cards = [chunk for chunk in result.metadata if chunk.type == "data-gene-set-list"]
    assert [ListedGeneSets.model_validate(card.data) for card in cards] == [
        ListedGeneSets(
            site_id="plasmodb",
            gene_sets=[
                ListedGeneSet(
                    id="gs-here",
                    name="Gametocyte kinases",
                    gene_count=2,
                    genes_here=2,
                    saved_on="plasmodb",
                    saved_here=True,
                ),
                ListedGeneSet(
                    id="gs-ortho",
                    name="3D7 strain gaps",
                    gene_count=3,
                    genes_here=2,
                    saved_on="orthomcl",
                    saved_here=False,
                    record_noun="protein",
                    out_of_date=_OUTGROWN,
                ),
            ],
        )
    ]
    assert [
        (row["genesHere"], row["recordNoun"]) for row in cards[0].data["geneSets"]
    ] == [(2, "gene"), (2, "protein")]
    rows = GeneSetListResponse.model_validate(result.return_value).gene_sets
    assert [row.out_of_date for row in rows] == [
        None,
        _OUTGROWN,
    ]
