"""Other sites' experiments come from the tool server's store, one card per site."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKSearchResponse
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import ExperimentCard
from veupathdb_mcp.embeddings import (
    ExperimentCardRow,
    IndexEntry,
    embedding_session,
    experiment_index_id,
    sync_index,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone._catalog_elsewhere import (
    ExperimentRead,
    rank_other_sites,
    read_experiment,
)
from pathfinder.tests._support.experiment_cards import CRYPTO_CARD, TOXO_CARD
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

pytestmark = pytest.mark.asyncio


async def _store(*cards: ExperimentCard) -> None:
    """Hold each card and index its text, as a catalog load of its site does."""
    async with embedding_session() as session:
        session.add_all(
            ExperimentCardRow(
                site_id=card.site_id,
                dataset_id=card.dataset_id,
                card=card.model_dump(mode="json", by_alias=True),
            )
            for card in cards
        )
        await session.commit()
    for card in cards:
        await sync_index(
            experiment_index_id(card.site_id),
            [IndexEntry(entry_id=card.dataset_id, text=card.index_text())],
        )


@pytest.fixture
async def two_sites(
    db_engine: AsyncEngine,
    patch_app_db_engine: None,
    embedding_index_cleaner: None,
) -> AsyncGenerator[None]:
    del patch_app_db_engine, embedding_index_cleaner
    await _store(CRYPTO_CARD, TOXO_CARD)
    yield
    async with db_engine.begin() as conn:
        await conn.exec_driver_sql("TRUNCATE TABLE experiment_cards")


async def test_a_ranked_card_is_read_and_its_references_recorded(
    two_sites: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    del two_sites
    orthologs = WDKSearchResponse.model_validate(
        load_recorded("search_genes_by_orthologs").json_body()
    ).search_data
    monkeypatch.setattr(
        catalog, "get_raw_searches", AsyncMock(return_value=[orthologs])
    )
    monkeypatch.setattr(
        catalog, "read_search_definition", AsyncMock(return_value=orthologs)
    )
    ctx = agent_run_context(agent_state=AgentToolState())

    ranked = await rank_other_sites(ctx, CRYPTO_CARD.index_text())
    ctx.deps.agent_state.record_elsewhere((match.card for match in ranked), frozenset())
    read = returned(await read_experiment(ctx, "DS_63b0de882c"), ExperimentRead)

    assert [(m.card.site_id, m.card.dataset_id) for m in ranked] == [
        ("cryptodb", "DS_63b0de882c")
    ]
    assert ranked[0].similarity == pytest.approx(1.0)
    assert (read.site, read.name, read.pmids) == (
        "cryptodb",
        "Transcriptome of 48 hours in vitro infection",
        ["26549794"],
    )
    assert ctx.deps.turn_markers.retrieved_sources == [
        "https://cryptodb.org/cryptodb/app/record/dataset/DS_63b0de882c",
        "26549794",
    ]


async def test_the_callers_own_site_is_never_ranked(two_sites: None) -> None:
    del two_sites
    ctx = agent_run_context(site_id="cryptodb", agent_state=AgentToolState())

    ranked = await rank_other_sites(ctx, CRYPTO_CARD.index_text())

    assert ranked == []
