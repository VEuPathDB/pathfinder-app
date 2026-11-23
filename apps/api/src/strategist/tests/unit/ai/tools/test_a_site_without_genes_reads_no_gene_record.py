"""A site that publishes no gene record class offers no gene record read, to the
Lead or to a check."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic_ai import RunContext, Tool
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset

from strategist.ai.agents import verification
from strategist.ai.explore import explore_agent
from strategist.ai.lead import lead_agent
from strategist.ai.lead.lead_agent import build_lead_toolset
from strategist.ai.tools.standalone import gene_record
from strategist.ai.tools.standalone.gene_record import (
    GeneRecordReader,
    offered_where_genes_are_held,
)
from strategist.ai.tools.toolsets.verification import build_toolset
from strategist.tests._support.tool_names import named_tools

_READ = ToolDefinition(name="read_gene_record")


async def _classes_of(site_id: str) -> dict[str, str]:
    return {
        "orthomcl": {"group": "Ortholog Groups", "sequence": "Proteins"},
        "plasmodb": {"transcript": "Genes", "compound": "Compounds"},
    }[site_id]


@pytest.fixture(autouse=True)
def _classes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gene_record, "record_class_names", _classes_of)


def _on(site_id: str) -> RunContext[GeneRecordReader]:
    return cast(
        "RunContext[GeneRecordReader]",
        SimpleNamespace(deps=SimpleNamespace(site_id=site_id)),
    )


async def test_only_a_site_with_genes_offers_the_record_read() -> None:
    offered = [
        await offered_where_genes_are_held(_on(site_id), _READ)
        for site_id in ("orthomcl", "plasmodb")
    ]

    assert offered == [None, _READ]


def _read_tool(toolset: AbstractToolset[Any]) -> Tool[Any]:
    while isinstance(toolset, WrapperToolset):
        toolset = toolset.wrapped
    assert isinstance(toolset, FunctionToolset)
    return toolset.tools["read_gene_record"]


@pytest.mark.parametrize("built", [build_lead_toolset, build_toolset])
def test_the_lead_and_the_check_offer_it_only_where_genes_are_held(
    built: Callable[[], AbstractToolset[Any]],
) -> None:
    assert _read_tool(built()).prepare is offered_where_genes_are_held


@pytest.mark.parametrize(
    "pinned",
    [
        lead_agent.pinned_gene_record_rule,
        explore_agent.pinned_gene_record_rule,
        verification.pinned_gene_record_rule,
    ],
)
async def test_the_record_read_is_named_only_where_it_is_offered(
    pinned: Callable[[Any], Awaitable[str | None]],
) -> None:
    told = [await pinned(_on(site_id)) for site_id in ("orthomcl", "plasmodb")]

    assert told[0] is None
    assert "read_gene_record" in named_tools(told[1] or "")


def test_a_check_on_a_site_without_genes_judges_the_sample_records() -> None:
    told = " ".join(verification._VERIFICATION_INSTRUCTIONS.split())

    assert "read_gene_record" not in named_tools(told)
    assert "such as OrthoMCL, has no gene record" in told
