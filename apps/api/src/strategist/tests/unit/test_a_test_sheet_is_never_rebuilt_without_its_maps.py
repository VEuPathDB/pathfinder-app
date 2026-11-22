"""A sheet formatted from a phyletic search cannot be rebuilt into its declarations."""

from __future__ import annotations

import pytest
from veupathdb_mcp.catalog import format_param_info_typed

from strategist.tests._support.recorded_searches import suite_search
from strategist.tests._support.sheets import declarations


def test_a_formatted_phyletic_sheet_is_refused_naming_the_recorded_path() -> None:
    sheet = format_param_info_typed(
        suite_search("search_genes_by_ortholog_pattern").parameters or []
    )

    with pytest.raises(ValueError, match="declared="):
        declarations(sheet)
