"""A site that publishes no gene record class offers no gene record read, to the
Lead or to a check."""

from __future__ import annotations

from collections.abc import Callable
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic_ai import RunContext, Tool
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets import AbstractToolset
from pydantic_ai.toolsets.function import FunctionToolset
from pydantic_ai.toolsets.wrapper import WrapperToolset

from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS
from pathfinder.ai.lead.lead_agent import build_lead_toolset
from pathfinder.ai.tools.standalone import gene_record
from pathfinder.ai.tools.standalone.gene_record import (
    GeneRecordReader,
    offered_where_genes_are_held,
)
from pathfinder.ai.tools.toolsets.verification import build_toolset

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


def test_a_check_reads_records_only_where_the_read_is_offered() -> None:
    told = " ".join(_VERIFICATION_INSTRUCTIONS.split())

    assert (
        "Where ``read_gene_record`` is offered, call it once per sampled gene" in told
    )
    assert "such as OrthoMCL, does not offer it" in told
