from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import ParameterNotOnSearch, VocabNarrowing


async def _no_pick(
    site_id: str,
    search_name: str,
    parameter_id: str,
    *,
    record_type: str | None = None,
    context_values: Mapping[str, object] | None = None,
    narrowing: VocabNarrowing | None = None,
) -> ParameterNotOnSearch:
    del site_id, record_type, context_values, narrowing
    return ParameterNotOnSearch(
        search_name=search_name,
        requested_parameter_id=parameter_id,
        message="",
        suggestions=[],
        valid_parameter_ids=[],
    )


def serve_no_vocabulary_pick(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(catalog, "read_parameter_options", _no_pick)
