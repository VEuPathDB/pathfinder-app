from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from pydantic_ai import ModelRetry
from veupathdb_mcp.catalog import UnlistedSearchError

from strategist.ai.tools.standalone import catalog_discovery
from strategist.tests.unit.ai.tools.conftest import agent_run_context


async def test_a_search_the_site_does_not_list_is_handed_back_to_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = AsyncMock(
        side_effect=UnlistedSearchError("veupathdb", "GenesByOrthorthologPattern")
    )
    monkeypatch.setattr(catalog_discovery, "read_parameter_options", read)

    with pytest.raises(ModelRetry, match="GenesByOrthorthologPattern") as retried:
        await catalog_discovery.get_parameter_options(
            agent_run_context(),
            search_name="GenesByOrthorthologPattern",
            parameter_id="excluded_species",
        )

    assert str(retried.value).endswith(
        "Find the search's exact name with search_for_searches."
    )
