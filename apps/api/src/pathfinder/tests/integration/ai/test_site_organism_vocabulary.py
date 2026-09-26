"""The organism list a site declares holds each strain entry whole, read live."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb_mcp.gene_lookup import list_organisms

from pathfinder.domain.strategy.organism_phrases import stated_organisms
from pathfinder.tests._support.site_organisms import recorded_organisms

pytestmark = [pytest.mark.live_wdk]

_S5 = (
    "Find Anopheles gambiae PEST genes with a predicted signal peptide and 2 to 99 "
    "transmembrane domains."
)


@pytest.fixture
def registered(require_wdk_creds: str) -> Generator[None]:
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(reset)


@pytest.mark.usefixtures("registered")
async def test_the_strain_is_one_entry_of_the_vectorbase_list() -> None:
    organisms = await list_organisms("vectorbase")

    assert "Anopheles gambiae PEST" in organisms
    assert [s.entry for s in stated_organisms(_S5, organisms)] == [
        "Anopheles gambiae PEST"
    ]


@pytest.mark.parametrize(
    ("site", "entry"),
    [
        ("vectorbase", "Anopheles gambiae PEST"),
        ("toxodb", "Neospora caninum Liverpool"),
        ("cryptodb", "Cryptosporidium parvum Iowa II"),
        ("plasmodb", "Plasmodium falciparum 3D7"),
        ("fungidb", "Aspergillus fumigatus Af293"),
    ],
)
@pytest.mark.usefixtures("registered")
async def test_the_recorded_entries_are_the_sites_own(site: str, entry: str) -> None:
    message = f"Find {entry} genes with a signal peptide"
    organisms = await list_organisms(site)

    assert [s.entry for s in stated_organisms(message, organisms)] == [entry]
    assert [s.entry for s in stated_organisms(message, recorded_organisms(site))] == [
        entry
    ]
