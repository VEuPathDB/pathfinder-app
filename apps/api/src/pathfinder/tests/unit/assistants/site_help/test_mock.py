"""The site-help script's arcs, run through the real agent."""

from __future__ import annotations

import pytest
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ToolReturnPart
from pydantic_ai.toolsets import FunctionToolset
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import RecordTypeInfo

from pathfinder.assistants.site_help import agent
from pathfinder.assistants.site_help.agent import (
    SiteHelpDeps,
    SiteSummary,
    build_site_help_agent,
)
from pathfinder.assistants.site_help.mock import (
    CHECK_MARKER,
    CHECK_REPLY,
    DESCRIBE_SITE_TOOL,
    LIST_SITES_TOOL,
    NOTHING_TO_PROCEED_REPLY,
    ORGANISMS_PROMPT,
    PROCEED_PREFIX,
    PROCEED_PROMPT,
    RECORD_TYPES_PROMPT,
    RECORD_TYPES_REPLY,
    SITES_REPLY,
    WDK_RECORD_TYPES_TOOL,
    build_site_help_mock,
)


async def wdk_list_record_types(site_id: str) -> list[str]:
    """Stands in for the served tool of the same name."""
    del site_id
    return ["transcript"]


def _deps(tool_sources: FunctionToolset[SiteHelpDeps] | None = None) -> SiteHelpDeps:
    return SiteHelpDeps(site_id="plasmodb", tool_sources=tool_sources)


def _tool_returns(messages: list[object]) -> list[ToolReturnPart]:
    return [
        part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]


async def test_the_marker_prompt_gets_the_fixed_reply() -> None:
    result = await build_site_help_agent().run(CHECK_MARKER, deps=_deps())

    assert result.output == CHECK_REPLY
    assert _tool_returns(list(result.all_messages())) == []


async def test_a_question_about_the_sites_calls_the_catalog_tool() -> None:
    result = await build_site_help_agent().run("which sites are there", deps=_deps())

    assert result.output == SITES_REPLY
    returns = _tool_returns(list(result.all_messages()))
    assert [part.tool_name for part in returns] == [LIST_SITES_TOOL]
    sites = returns[0].content
    assert isinstance(sites, list)
    ids = {site.site_id for site in sites if isinstance(site, SiteSummary)}
    assert {"plasmodb", "toxodb", "vectorbase"} <= ids


async def test_a_tool_the_turn_s_source_serves_is_one_the_agent_can_call() -> None:
    """A source resolved for this turn reaches the agent through its deps."""
    served: FunctionToolset[SiteHelpDeps] = FunctionToolset([wdk_list_record_types])

    result = await build_site_help_agent().run(
        RECORD_TYPES_PROMPT,
        deps=_deps(served),
    )

    returns = _tool_returns(list(result.all_messages()))
    assert [part.tool_name for part in returns] == [WDK_RECORD_TYPES_TOOL]
    assert result.output == RECORD_TYPES_REPLY


async def test_anything_else_falls_through_to_the_echo() -> None:
    result = await build_site_help_agent().run("tell me about kinases", deps=_deps())

    assert result.output == "[mock] tell me about kinases"
    assert _tool_returns(list(result.all_messages())) == []


async def test_a_bare_approval_names_the_request_the_history_carries() -> None:
    """The arc answers from the run's earlier messages, not from its prompt."""
    agent = build_site_help_agent()
    first = await agent.run("which sites are there", deps=_deps())

    result = await agent.run(
        PROCEED_PROMPT,
        deps=_deps(),
        message_history=list(first.all_messages()),
    )

    assert result.output == f"{PROCEED_PREFIX}which sites are there"


async def test_a_bare_approval_with_no_history_has_nothing_to_proceed_with() -> None:
    result = await build_site_help_agent().run(PROCEED_PROMPT, deps=_deps())

    assert result.output == NOTHING_TO_PROCEED_REPLY


async def test_an_agent_with_no_site_help_tool_gets_the_last_prompt_line() -> None:
    """The conversation-title agent offers no tools and must still get text."""
    titles: Agent[None, str] = Agent(
        build_site_help_mock(),
        output_type=str,
        instructions="Title it.",
        name="conversation-title",
    )

    result = await titles.run("User's first message:\nwhich sites are there")

    assert result.output == "which sites are there"


async def test_the_organism_question_is_answered_from_the_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scripted answer quotes the species the describe tool returned."""

    async def _organisms(site_id: str) -> list[str]:
        del site_id
        return [
            "Toxoplasma gondii ME49",
            "Toxoplasma gondii GT1",
            "Hammondia hammondi H.H.34",
            "Besnoitia besnoiti",
        ]

    async def _record_types(site_id: str) -> list[RecordTypeInfo]:
        del site_id
        return [RecordTypeInfo(name="transcript", display_name="Genes")]

    async def _searches(site_id: str, record_type: str) -> list[WDKSearch]:
        del site_id, record_type
        return []

    monkeypatch.setattr(agent, "list_organisms", _organisms)
    monkeypatch.setattr(agent, "get_record_types", _record_types)
    monkeypatch.setattr(agent, "get_raw_searches", _searches)

    result = await build_site_help_agent().run(ORGANISMS_PROMPT, deps=_deps())

    returns = _tool_returns(list(result.all_messages()))
    assert [part.tool_name for part in returns] == [DESCRIBE_SITE_TOOL]
    assert "Toxoplasma gondii (2 strains)" in result.output
    assert "Hammondia hammondi (1 strain)" in result.output
    assert result.output.endswith("Besnoitia besnoiti.")
    assert "Besnoitia besnoiti (" not in result.output
