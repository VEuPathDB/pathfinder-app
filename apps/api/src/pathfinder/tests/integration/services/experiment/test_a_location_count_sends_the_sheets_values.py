"""A read-only count of a location search sends what a step of it sends, so
hostdb answers the count instead of a server error.

Gated on WDK_TEST_TOKEN, or WDK_TEST_EMAIL/WDK_TEST_PASSWORD (skipped unset).
"""

from __future__ import annotations

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx

from pathfinder.ai.tools.standalone._variant_targets import resolved_variants
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.experiment.search_reads import search_count
from pathfinder.services.experiment.variant_comparison import VariantInput

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]


def _chromosome_19() -> VariantInput:
    return VariantInput.model_validate(
        {
            "label": "chromosome 19",
            "searchName": "GenesByLocation",
            "parameters": {
                "organismSinglePick": {
                    "type": "multi-pick-vocabulary",
                    "values": ["Mus musculus C57BL6J"],
                },
                "chromosomeOptional": {"type": "single-pick-vocabulary", "value": "19"},
            },
        }
    )


async def test_a_location_count_on_hostdb_answers_with_the_sheets_values(
    require_wdk_creds: str,
    patch_app_db_engine: None,
) -> None:
    del patch_app_db_engine
    handle = veupathdb_auth_token_ctx.set(require_wdk_creds)
    try:
        (spec,) = await resolved_variants(
            StrategySession(site_id="hostdb"), [_chromosome_19()]
        )
        counted = await search_count("hostdb", spec)
    finally:
        veupathdb_auth_token_ctx.reset(handle)

    assert counted.values["sequenceId"] == "(Example: chr22)"
    assert counted.gene_count > 0
