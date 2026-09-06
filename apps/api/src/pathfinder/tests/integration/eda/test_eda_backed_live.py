"""The census the predicate is built on, re-measured.

Gated on WDK_TEST_TOKEN, or WDK_TEST_EMAIL/WDK_TEST_PASSWORD (skipped unset).
"""

from __future__ import annotations

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb_mcp.catalog.eda_backed import list_eda_backed
from veupathdb_mcp.catalog.searches import get_raw_searches

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_NAME_FILTER_UNDERCOUNT = 3
_MIN_EDA_BACKED = 60
_MIN_COMPUTE_BACKED = 50


async def test_the_predicate_finds_far_more_than_a_name_filter(
    require_wdk_creds: str,
    patch_app_db_engine: None,
) -> None:
    """The search catalog is indexed in Postgres, so the census reads it there."""
    del patch_app_db_engine
    handle = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        searches = await get_raw_searches("plasmodb", "transcript")
        described = await list_eda_backed("plasmodb", "transcript")
    finally:
        veupathdb_auth_token_ctx.reset(handle)
    by_name = [s for s in searches if "Eda" in s.url_segment]
    assert len(described) >= _MIN_EDA_BACKED
    assert len(described) > len(by_name) * _NAME_FILTER_UNDERCOUNT


async def test_the_compute_backed_searches_are_the_majority(
    require_wdk_creds: str,
    patch_app_db_engine: None,
) -> None:
    del patch_app_db_engine
    handle = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        described = await list_eda_backed("plasmodb", "transcript")
    finally:
        veupathdb_auth_token_ctx.reset(handle)
    compute_backed = [d for d in described if d.is_compute_backed]
    assert len(compute_backed) >= _MIN_COMPUTE_BACKED


async def test_exactly_one_search_declares_the_spec_and_never_reads_it(
    require_wdk_creds: str,
    patch_app_db_engine: None,
) -> None:
    del patch_app_db_engine
    handle = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        described = await list_eda_backed("plasmodb", "transcript")
    finally:
        veupathdb_auth_token_ctx.reset(handle)
    inert = [d for d in described if not d.reads_the_spec]
    assert len(inert) == 1
    assert inert[0].query_name == "GenesByWGCNAModule"
