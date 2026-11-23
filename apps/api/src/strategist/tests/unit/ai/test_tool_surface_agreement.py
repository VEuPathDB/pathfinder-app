"""The tools an agent's instructions rely on are the tools its toolsets register."""

from __future__ import annotations

import importlib

import pytest

from strategist.ai.tools.toolsets.verification import build_toolset
from strategist.tests._support.agent_texts import BUILT
from strategist.tests._support.sub_agents import agent_tool_names, toolset_tool_names
from strategist.tests._support.tool_names import served_tool_names


def _all_registered_names() -> set[str]:
    return {name for build in BUILT.values() for name in agent_tool_names(build())}


def test_verify_toolset_contains_instructed_gene_chain() -> None:
    """VERIFY resolves a gene name to its ID through a chain its toolset registers."""
    names = toolset_tool_names(build_toolset())
    for tool in ("lookup_gene_records", "resolve_gene_ids_to_records"):
        assert tool in names, f"{tool} is instructed by VERIFY but not registered"


def test_the_research_reads_are_served_and_not_registered() -> None:
    """The two research tools reach an agent through the source, not a toolset."""
    assert {
        "research_literature_search",
        "research_web_search",
    } == served_tool_names()
    assert served_tool_names() & _all_registered_names() == set()


def test_update_search_decision_absent() -> None:
    """The superseded discovery-decision tool no longer exists."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("strategist.ai.tools.standalone.catalog_selection")
