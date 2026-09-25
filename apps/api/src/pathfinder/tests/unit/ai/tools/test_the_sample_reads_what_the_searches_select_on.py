"""A check's sample of the root carries the attributes its searches select on,
read from the catalog, so a gene's fit is judged from the site's own values."""

from __future__ import annotations

import asyncio

import pytest
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.wdk import WDKRecordType, WDKSearch
from veupathdb_mcp import ToolErrorPayload
from veupathdb_mcp.wdk import SampleRecordsResult

from pathfinder.ai.tools.standalone import _sample_attributes, results
from pathfinder.ai.tools.standalone._sample_attributes import selecting_attributes
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context

# The defaults the site lists, as plasmodb's expanded catalog records them.
_SIGNAL_PEPTIDE = WDKSearch(
    url_segment="GenesWithSignalPeptide",
    default_attributes=[
        "primary_key",
        "organism",
        "gene_location_text",
        "gene_product",
        "signalp_41_probability",
        "signalp_50_probability",
        "signalp_60_probability",
        "matched_result",
    ],
)
_TRANSMEMBRANE = WDKSearch(
    url_segment="GenesByTransmembraneDomains",
    default_attributes=[
        "primary_key",
        "organism",
        "gene_location_text",
        "gene_product",
        "tm_count",
        "matched_result",
    ],
)
_GENERIC = [
    WDKSearch(
        url_segment=f"GenesByGeneric{index}",
        default_attributes=[
            "primary_key",
            "organism",
            "gene_location_text",
            "gene_product",
        ],
    )
    for index in range(10)
]
_SEARCHES = [_SIGNAL_PEPTIDE, _TRANSMEMBRANE, *_GENERIC]
_RECORD_ATTRIBUTES = frozenset(
    {
        "primary_key",
        "organism",
        "gene_location_text",
        "gene_product",
        "signalp_41_probability",
        "signalp_50_probability",
        "signalp_60_probability",
        "tm_count",
    }
)


def test_the_attributes_are_what_few_other_searches_show() -> None:
    assert selecting_attributes(
        _SEARCHES,
        _RECORD_ATTRIBUTES,
        ["GenesWithSignalPeptide", "GenesByTransmembraneDomains"],
    ) == [
        "signalp_41_probability",
        "signalp_50_probability",
        "signalp_60_probability",
        "tm_count",
    ]


def test_a_search_the_catalog_does_not_list_adds_nothing() -> None:
    assert selecting_attributes(_SEARCHES, _RECORD_ATTRIBUTES, ["GenesByNothing"]) == []


def test_a_dynamic_column_of_one_search_is_not_asked_of_the_root() -> None:
    """``matched_result`` is a column of the leaf's own answer, not a record attribute."""
    assert "matched_result" not in selecting_attributes(
        _SEARCHES, _RECORD_ATTRIBUTES, ["GenesWithSignalPeptide"]
    )


def _signal_peptide_and_transmembrane() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("g1", "exported membrane proteins", "plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_and",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(
                id="step_sp", search_name="GenesWithSignalPeptide"
            ),
            secondary_input=StrategyStepNode(
                id="step_tm", search_name="GenesByTransmembraneDomains"
            ),
        )
    )
    graph.recompute_roots()
    session.graph = graph
    return session


async def test_the_root_sample_asks_for_the_leaves_attributes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[list[str] | None] = []

    async def searches(site_id: str, record_type: str) -> list[WDKSearch]:
        assert (site_id, record_type) == ("plasmodb", "transcript")
        return _SEARCHES

    async def record_types(site_id: str) -> list[WDKRecordType]:
        assert site_id == "plasmodb"
        return [
            WDKRecordType.model_validate(
                {
                    "urlSegment": "transcript",
                    "attributes": [{"name": n} for n in sorted(_RECORD_ATTRIBUTES)],
                }
            )
        ]

    async def sample(
        site_id: str, step_id: int, *, limit: int, attributes: list[str] | None
    ) -> SampleRecordsResult:
        del site_id, limit
        asked.append(attributes)
        return SampleRecordsResult(step_id=step_id, total_count=0)

    monkeypatch.setattr(_sample_attributes, "get_raw_searches", searches)
    monkeypatch.setattr(_sample_attributes, "get_raw_record_types", record_types)
    monkeypatch.setattr(results, "step_sample_records", sample)

    await results.get_sample_records(
        agent_run_context(strategy_session=_signal_peptide_and_transmembrane()), 42
    )

    assert asked == [
        [
            "gene_product",
            "gene_name",
            "organism",
            "signalp_41_probability",
            "signalp_50_probability",
            "signalp_60_probability",
            "tm_count",
        ]
    ]


async def test_a_sample_the_site_does_not_answer_in_time_is_a_warning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read is bounded, so a check goes on without the sample."""

    async def selected(site_id: str, record_type: str, graph: object) -> list[str]:
        del site_id, record_type, graph
        return []

    async def never(
        site_id: str, step_id: int, *, limit: int, attributes: list[str] | None
    ) -> SampleRecordsResult:
        del site_id, limit, attributes
        await asyncio.sleep(60)
        return SampleRecordsResult(step_id=step_id, total_count=0)

    monkeypatch.setattr(results, "sample_attributes", selected)
    monkeypatch.setattr(results, "step_sample_records", never)
    monkeypatch.setattr(results, "SAMPLE_DEADLINE_SECONDS", 0.01)

    answer = await results.get_sample_records(
        agent_run_context(strategy_session=_signal_peptide_and_transmembrane()), 42
    )

    assert returned(answer, ToolErrorPayload).model_dump(
        include={"code", "message"}
    ) == {
        "code": "WDK_ERROR",
        "message": (
            "The site did not answer the sample of step 42 within 0.01 s. Go on "
            "without it and say that the genes were not sampled."
        ),
    }
