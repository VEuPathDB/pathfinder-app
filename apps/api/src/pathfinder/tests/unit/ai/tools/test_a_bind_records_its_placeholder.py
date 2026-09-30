"""A bind records whether a value is a placeholder, read from the parameter's sheet."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.catalog import format_param_info_typed

from pathfinder.ai.tools.standalone._frame_sources import bound_values
from pathfinder.tests._support.recorded_searches import client_search


def _bind(value: str) -> tuple[str, bool]:
    infos = format_param_info_typed(
        client_search("search_genes_by_location").parameters or []
    )
    bound = bound_values(
        {"sequenceId": StringValue(value=value)},
        infos=infos,
        site_supplied=set(),
        request_texts=["genes on chromosome 17"],
        reason="",
    )["sequenceId"]
    return bound.source, bound.placeholder


def test_the_sites_example_prompt_is_a_placeholder_default() -> None:
    assert _bind("(Example: Pf3D7_04_v3)") == ("default", True)


def test_a_sequence_id_is_no_placeholder() -> None:
    assert _bind("Pf3D7_04_v3") == ("chosen", False)
