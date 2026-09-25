"""A dataset record in the experiment store, so a study reads as published by a site."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import delete
from veupathdb.wdk import get_site
from veupathdb_mcp.catalog import ExperimentCard
from veupathdb_mcp.embeddings import ExperimentCardRow, embedding_session


@asynccontextmanager
async def published_on(
    site_id: str, dataset_id: str, *, organism: str
) -> AsyncIterator[None]:
    """The site's dataset report holds the study's dataset while the block runs."""
    card = ExperimentCard(
        site_id=site_id,
        dataset_id=dataset_id,
        name=f"Dataset {dataset_id}",
        organism=organism,
        assay="Phenotype",
        record_url=f"{get_site(site_id).web_base_url}/app/record/dataset/{dataset_id}",
    )
    async with embedding_session() as session:
        session.add(
            ExperimentCardRow(
                site_id=site_id,
                dataset_id=dataset_id,
                card=card.model_dump(mode="json", by_alias=True),
            )
        )
        await session.commit()
    try:
        yield
    finally:
        async with embedding_session() as session:
            await session.execute(
                delete(ExperimentCardRow).where(
                    ExperimentCardRow.site_id == site_id,
                    ExperimentCardRow.dataset_id == dataset_id,
                )
            )
            await session.commit()
