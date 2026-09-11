"""Enrichment survives reopening the workbench.

``run_enrichment`` computed the analysis, returned it, and dropped it. Nothing
wrote it down, so a researcher who reopened the workbench saw the gene set with
no analysis attached - and no indication it had ever been run. Enrichment is a
slow WDK round trip, so that is not just a display bug: they pay for it again.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from veupathdb_mcp.wdk.enrichment import EnrichmentResult

from pathfinder.persistence.models import User
from pathfinder.services.gene_sets import operations
from pathfinder.services.gene_sets.operations import GeneSetService
from pathfinder.services.gene_sets.store import GeneSetStore
from pathfinder.services.gene_sets.types import GeneSet


@pytest.fixture
async def db_session(
    session_maker: async_sessionmaker[AsyncSession],
    db_cleaner: None,
) -> AsyncGenerator[AsyncSession]:
    del db_cleaner
    async with session_maker() as session:
        yield session


@pytest.fixture
async def seed_user(db_session: AsyncSession) -> User:
    user = User(id=uuid4())
    db_session.add(user)
    await db_session.flush()
    await db_session.commit()
    return user


def _result(term: str) -> EnrichmentResult:
    return EnrichmentResult.model_validate(
        {
            "analysisType": "go_function",
            "terms": [
                {
                    "termId": term,
                    "termName": "protein kinase activity",
                    "geneCount": 12,
                    "backgroundCount": 105,
                    "foldEnrichment": 3.48,
                    "oddsRatio": 3.4,
                    "pValue": 1e-13,
                    "fdr": 1e-11,
                    "bonferroni": 1e-10,
                }
            ],
            "totalGenesAnalyzed": 40,
            "backgroundSize": 5000,
        }
    )


async def test_enrichment_is_still_there_after_a_reload(
    patch_app_db_engine: None,
    seed_user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del patch_app_db_engine
    store = GeneSetStore()
    service = GeneSetService(store)
    gs = GeneSet(
        id="gs1",
        name="Kinases",
        site_id="plasmodb",
        gene_ids=["PF3D7_0100100"],
        source="paste",
        user_id=seed_user.id,
        wdk_step_id=100,
        search_name="GenesByTaxon",
    )
    store.save(gs)
    await service.flush(gs.id)

    async def _fake_batch(**_kwargs: Any) -> tuple[list[EnrichmentResult], list[str]]:
        return [_result("GO:0004672")], []

    monkeypatch.setattr(
        operations.EnrichmentService, "run_batch", staticmethod(_fake_batch)
    )

    returned = await service.run_enrichment(seed_user.id, "gs1", ["go_function"])
    assert len(returned) == 1

    # A fresh store: nothing cached, so this is what the database holds.
    reloaded = await GeneSetStore().aget("gs1")

    assert reloaded is not None
    assert len(reloaded.enrichment_results) == 1
    assert reloaded.enrichment_results[0].terms[0].term_id == "GO:0004672"


async def test_a_set_with_no_enrichment_reloads_empty_not_missing(
    patch_app_db_engine: None,
    seed_user: User,
) -> None:
    """The column defaults to an empty list, so older rows load cleanly."""
    del patch_app_db_engine
    store = GeneSetStore()
    service = GeneSetService(store)
    gs = GeneSet(
        id="gs2",
        name="Untouched",
        site_id="plasmodb",
        gene_ids=["PF3D7_0100200"],
        source="paste",
        user_id=seed_user.id,
    )
    store.save(gs)
    await service.flush(gs.id)

    reloaded = await GeneSetStore().aget("gs2")

    assert reloaded is not None
    assert reloaded.enrichment_results == []
