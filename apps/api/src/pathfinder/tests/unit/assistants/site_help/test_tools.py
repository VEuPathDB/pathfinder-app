"""The pilot's two read-only tools, over the real site registry."""

from __future__ import annotations

from typing import Any, cast

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.tools import RunContext
from veupathdb_mcp.catalog import RecordTypeInfo

from pathfinder.assistants.site_help import agent
from pathfinder.assistants.site_help.agent import (
    SiteHelpDeps,
    describe_site,
    list_veupathdb_sites,
)


class _Ctx:
    tool_call_id = "call_1"


def _ctx() -> RunContext[SiteHelpDeps]:
    return cast("RunContext[SiteHelpDeps]", _Ctx())


async def test_it_lists_the_registered_sites_with_their_urls() -> None:
    sites = (await list_veupathdb_sites(_ctx())).return_value

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

    async def _searches(site_id: str, record_type: str) -> list[Any]:
        del site_id
        return ["a", "b", "c"] if record_type == "transcript" else []

    monkeypatch.setattr(agent, "get_record_types", _record_types)
    monkeypatch.setattr(agent, "get_raw_searches", _searches)

    detail = (await describe_site(_ctx(), "plasmodb")).return_value

    assert detail.site_id == "plasmodb"
    assert detail.display_name
    assert [(rt.name, rt.search_count) for rt in detail.record_types] == [
        ("transcript", 3),
        ("organism", 0),
    ]
