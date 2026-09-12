"""The pilot's two read-only tools, over the real site registry."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import RunContext
from pydantic_ai.usage import RunUsage
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import RecordTypeInfo

from pathfinder.assistants.site_help import agent
from pathfinder.assistants.site_help.agent import (
    SiteDetail,
    SiteHelpDeps,
    SiteSummary,
    describe_site,
    list_veupathdb_sites,
)
from pathfinder.tests._support.tool_returns import returned


def _ctx() -> RunContext[SiteHelpDeps]:
    return RunContext(
        deps=SiteHelpDeps(site_id="plasmodb"),
        model=TestModel(),
        usage=RunUsage(),
        messages=[],
        tool_call_id="call_1",
    )


async def test_it_lists_the_registered_sites_with_their_urls() -> None:
    sites = returned(await list_veupathdb_sites(_ctx()), list[SiteSummary])

    by_id = {site.site_id: site for site in sites}
    assert {"plasmodb", "toxodb", "vectorbase"} <= set(by_id)
    assert by_id["plasmodb"].url.startswith("https://")
    assert by_id["plasmodb"].display_name


async def test_an_unknown_site_is_answered_with_the_ids_that_exist() -> None:
    """The model picked a name; it is told the real ones rather than a 404."""
    with pytest.raises(ModelRetry) as raised:
        await describe_site(_ctx(), "plasmadb")

    assert "plasmodb" in str(raised.value)


async def test_it_counts_the_searches_of_each_record_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catalog reads are the services'; the join and the counts are ours."""

    async def _record_types(site_id: str) -> list[RecordTypeInfo]:
        assert site_id == "plasmodb"
        return [
            RecordTypeInfo(name="transcript", display_name="Genes"),
            RecordTypeInfo(name="organism", display_name="Organisms"),
        ]

    async def _searches(site_id: str, record_type: str) -> list[WDKSearch]:
        del site_id
        if record_type != "transcript":
            return []
        return [WDKSearch(url_segment=f"search_{index}") for index in range(3)]

    monkeypatch.setattr(agent, "get_record_types", _record_types)
    monkeypatch.setattr(agent, "get_raw_searches", _searches)

    detail = returned(await describe_site(_ctx(), "plasmodb"), SiteDetail)

    assert detail.site_id == "plasmodb"
    assert detail.display_name
    assert [(rt.name, rt.search_count) for rt in detail.record_types] == [
        ("transcript", 3),
        ("organism", 0),
    ]
