"""Seeding a published study over a card the catalog already holds replaces it."""

from __future__ import annotations

from sqlalchemy import select
from veupathdb_mcp.embeddings import ExperimentCardRow, embedding_session

from pathfinder.tests._support.published_studies import published_on

SITE = "plasmodb"
DATASET = "DS_seed_twice"


async def test_a_seed_over_an_existing_card_replaces_it(db_cleaner: None) -> None:
    del db_cleaner
    async with (
        published_on(SITE, DATASET, organism="Plasmodium falciparum 3D7"),
        published_on(SITE, DATASET, organism="Plasmodium vivax P01"),
        embedding_session() as session,
    ):
        rows = (
            (
                await session.execute(
                    select(ExperimentCardRow.card).where(
                        ExperimentCardRow.site_id == SITE,
                        ExperimentCardRow.dataset_id == DATASET,
                    )
                )
            )
            .scalars()
            .all()
        )

    assert len(rows) == 1
    assert rows[0]["organism"] == "Plasmodium vivax P01"
