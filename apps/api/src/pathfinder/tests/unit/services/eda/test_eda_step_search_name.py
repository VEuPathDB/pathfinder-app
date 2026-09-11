"""The mapping from export kind to EDA-backed search is stated once."""

from __future__ import annotations

from veupathdb_mcp.catalog import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.services.eda.steps import eda_search_name


def test_a_subset_export_uses_the_generic_subset_search() -> None:
    assert eda_search_name(is_compute_backed=False) == "GenesByEdaSubset"
    assert eda_search_name(is_compute_backed=False) == SUBSET_QUERY


def test_a_volcano_export_uses_the_viz_with_compute_search() -> None:
    """GeneEdaVizWithComputePlugin reads the first computation's volcano."""
    assert eda_search_name(is_compute_backed=True) == "GenesByEdaVizWithCompute"
    assert eda_search_name(is_compute_backed=True) == COMPUTE_QUERY
