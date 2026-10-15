"""A step's sample is read under the step's own record type, with the columns its
own search shows: a BLAST step under a group root reads each protein's E-value."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKAttributeField, WDKRecordType, WDKSearch, WDKStepTree
from veupathdb_mcp.wdk import SampleRecordsResult

from pathfinder.ai.tools.standalone import _sample_attributes, results
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies.sync_state import WDKSyncState

from .conftest import agent_run_context

_BLAST_STEP = 227256640
_GROUPS_STEP = 227256650
# The defaults and the added columns qa.orthomcl.org lists for each search.
_BY_BLAST = WDKSearch(
    url_segment="ByBlast",
    default_attributes=[
        "primary_key",
        "taxon_name",
        "product",
        "length",
        "ec_numbers",
        "pfam_domains",
        "core_peripheral",
        "group_link",
        "score",
        "evalue",
    ],
    dynamic_attributes=[
        WDKAttributeField(name=n)
        for n in (
            "evalue_mant",
            "evalue_exp",
            "score",
            "summary",
            "alignment",
            "evalue",
        )
    ],
)
_GROUPS_FROM_SEQUENCES = WDKSearch(
    url_segment="GroupsFromSequences",
    default_attributes=["primary_key", "number_of_members", "keywords", "descriptions"],
    dynamic_attributes=[WDKAttributeField(name="wdk_weight")],
)
_SEARCHES = {"sequence": [_BY_BLAST], "group": [_GROUPS_FROM_SEQUENCES]}


def _blast_then_groups() -> StrategySession:
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph("g1", "groups of a protein's BLAST hits", "orthomcl")
    graph.record_type = "group"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="groups",
            search_name="GroupsFromSequences",
            primary_input=StrategyStepNode(id="blast", search_name="ByBlast"),
        )
    )
    graph.steps["blast"].record_class = "sequence"
    graph.steps["groups"].record_class = "group"
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={"blast": _BLAST_STEP, "groups": _GROUPS_STEP},
        wdk_step_tree=WDKStepTree(
            step_id=_GROUPS_STEP, primary_input=WDKStepTree(step_id=_BLAST_STEP)
        ),
    )
    return session


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[str] | None]]:
    seen: list[tuple[str, list[str] | None]] = []

    async def searches(site_id: str, record_type: str) -> list[WDKSearch]:
        assert site_id == "orthomcl"
        return _SEARCHES[record_type]

    async def record_types(site_id: str) -> list[WDKRecordType]:
        del site_id
        return []

    async def sample(
        site_id: str,
        step_id: int,
        *,
        limit: int,
        attributes: list[str] | None,
        record_type: str,
        seed: str,
    ) -> results.SampledRecords:
        del site_id, limit, seed
        seen.append((record_type, attributes))
        return results.SampledRecords(
            SampleRecordsResult(step_id=step_id, total_count=0), []
        )

    monkeypatch.setattr(_sample_attributes, "get_raw_searches", searches)
    monkeypatch.setattr(_sample_attributes, "get_raw_record_types", record_types)
    monkeypatch.setattr(results, "sample_page", sample)
    return seen


async def test_the_blast_step_reads_each_protein_with_its_evalue(
    asked: list[tuple[str, list[str] | None]],
) -> None:
    await results.get_sample_records(
        agent_run_context(strategy_session=_blast_then_groups()), _BLAST_STEP
    )

    assert asked == [
        (
            "sequence",
            [
                "taxon_name",
                "product",
                "length",
                "ec_numbers",
                "pfam_domains",
                "core_peripheral",
                "group_link",
                "score",
                "evalue",
            ],
        )
    ]


async def test_the_group_root_reads_each_group_with_its_own_columns(
    asked: list[tuple[str, list[str] | None]],
) -> None:
    await results.get_sample_records(
        agent_run_context(strategy_session=_blast_then_groups())
    )

    assert asked == [
        ("group", ["number_of_members", "keywords", "descriptions"]),
    ]
