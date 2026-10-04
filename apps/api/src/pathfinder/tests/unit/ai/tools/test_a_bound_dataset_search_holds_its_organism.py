"""``set_criterion`` holds the organisms of the dataset a search runs on."""

from __future__ import annotations

import pytest
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.tests._support.organism_reads import DATASETS
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    bind,
    param_info,
    serve_search,
)

_OOCYSTS = "GenesByRNASeqchomTU502_Widmer_oocysts_ebi_rnaSeq_RSRCPercentile"


def _percentile_sheet(_context: dict[str, str]) -> list[ParameterInfo]:
    return [
        param_info("min_expression_percentile", display_name="Minimum percentile"),
        param_info(
            "max_expression_percentile",
            display_name="Maximum percentile",
            required=False,
            default_value="100",
        ),
    ]


async def test_a_bound_dataset_search_holds_its_datasets_organism(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, _percentile_sheet)
    state = AgentToolState()

    await bind(
        state,
        _OOCYSTS,
        {"min_expression_percentile": "80", "max_expression_percentile": None},
        text="genes expressed in C. hominis oocysts",
    )

    (criterion,) = state.operational_spec_draft.criteria
    assert DATASETS[_OOCYSTS] == ["Cryptosporidium hominis TU502"]
    assert (criterion.organism_param, criterion.dataset_organisms) == (
        None,
        ["Cryptosporidium hominis TU502"],
    )


async def test_a_search_no_one_dataset_names_holds_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_search(monkeypatch, _percentile_sheet)
    state = AgentToolState()

    await bind(
        state,
        "GenesBySingleCell",
        {"min_expression_percentile": "80", "max_expression_percentile": None},
        text="genes expressed in single cells",
    )

    (criterion,) = state.operational_spec_draft.criteria
    assert criterion.dataset_organisms == []
