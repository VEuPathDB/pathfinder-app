from __future__ import annotations

import inspect
from typing import Any

import pytest
from pydantic_ai import Tool
from veupathdb_mcp import MAX_CALL_SECONDS_META_KEY
from veupathdb_mcp.audit import RECORD_READS_PER_CALL
from veupathdb_mcp.gene_lookup import GeneResolveResult, GeneResult
from veupathdb_mcp.server import TOOLS

from pathfinder.ai.tools.standalone import control_sets, gene
from pathfinder.ai.tools.standalone.catalog import (
    browse_search_categories,
    list_searches,
    list_transforms,
    lookup_phyletic_codes,
    search_for_searches,
)
from pathfinder.ai.tools.standalone.control_sets import build_control_set
from pathfinder.ai.tools.standalone.gene import resolve_gene_ids_to_records
from pathfinder.ai.tools.standalone.gene_sets import save_gene_set
from pathfinder.services.experiment.control_sourcing import ResolvedControls
from pathfinder.tests._support.database import detached_session
from pathfinder.tests._support.orthomcl_gene_class import (
    NO_GENE_RECORDS,
    ORTHOMCL,
    held_record_types,
    orthomcl_gene_class,
)
from pathfinder.tests._support.orthomcl_record_classes import (
    serve_orthomcl_record_classes,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context


def _arguments(tool: Tool[Any]) -> tuple[set[str], set[str]]:
    schema = tool.function_schema.json_schema
    return set(schema["properties"]), set(schema.get("required", []))


def test_a_catalog_read_names_its_record_type_and_a_gene_tool_takes_none() -> None:
    readers: list[Tool[Any]] = [
        Tool(search_for_searches),
        Tool(browse_search_categories),
        Tool(list_searches),
        Tool(list_transforms),
    ]
    derived: list[Tool[Any]] = [
        Tool(lookup_phyletic_codes),
        Tool(resolve_gene_ids_to_records),
        Tool(save_gene_set),
        Tool(build_control_set),
    ]

    assert [("record_type" in _arguments(t)[1]) for t in readers] == [True] * 4
    assert [("record_type" in _arguments(t)[0]) for t in derived] == [False] * 4


@pytest.mark.parametrize(
    ("site_id", "read_under"), [("plasmodb", "transcript"), ("orthomcl", "")]
)
async def test_the_phyletic_tree_is_read_under_the_class_the_site_lists_it(
    monkeypatch: pytest.MonkeyPatch, site_id: str, read_under: str
) -> None:
    if site_id == "orthomcl":
        serve_orthomcl_record_classes(monkeypatch)
    asked: list[str] = []

    async def _lookup(_site_id: str, record_type: str, _query: str) -> dict[str, Any]:
        asked.append(record_type)
        return {"matches": [], "total": 0}

    monkeypatch.setattr("veupathdb_mcp.catalog.lookup_phyletic_codes", _lookup)

    await lookup_phyletic_codes(agent_run_context(site_id=site_id), "human")

    assert asked == [read_under]


async def test_gene_ids_are_read_by_record_and_upload_no_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, list[str]]] = []

    async def _read(site_id: str, gene_ids: list[str]) -> GeneResolveResult:
        asked.append((site_id, gene_ids))
        return GeneResolveResult(
            records=[GeneResult(gene_id=g) for g in gene_ids], total_count=1
        )

    monkeypatch.setattr(gene, "read_gene_ids", _read)
    found = returned(
        await resolve_gene_ids_to_records(agent_run_context(), [" PF3D7_1222600 "]),
        GeneResolveResult,
    )

    assert (asked, [r.gene_id for r in found.records]) == (
        [("plasmodb", ["PF3D7_1222600"])],
        ["PF3D7_1222600"],
    )


async def test_a_site_with_no_gene_records_refuses_the_read_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held_record_types(monkeypatch)

    with orthomcl_gene_class() as wire:
        refused = returned(
            await resolve_gene_ids_to_records(
                agent_run_context(site_id=ORTHOMCL), ["PF3D7_1133400"]
            ),
            GeneResolveResult,
        )

    assert (refused.records, refused.error) == ([], NO_GENE_RECORDS)
    assert (wire.gene_reads.call_count, wire.record_type_reads.call_count) == (1, 0)


async def test_more_ids_than_one_call_reads_are_refused_before_any_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _read(site_id: str, gene_ids: list[str]) -> GeneResolveResult:
        raise AssertionError((site_id, gene_ids))

    monkeypatch.setattr(gene, "read_gene_ids", _read)
    ids = [f"PF3D7_{k:07d}" for k in range(RECORD_READS_PER_CALL + 1)]
    refused = returned(
        await resolve_gene_ids_to_records(agent_run_context(), ids), GeneResolveResult
    )

    assert refused.error == "Too many IDs (max 80). Reduce the list."


def test_the_read_keeps_the_budget_the_served_tool_declares() -> None:
    [served] = [
        row.meta for row in TOOLS if row.fn.__name__ == "resolve_gene_ids_to_records"
    ]

    assert served == {MAX_CALL_SECONDS_META_KEY: gene.RESOLVE_MAX_CALL_SECONDS}
    assert gene.RESOLVE_MAX_CALL_SECONDS == 120


async def test_controls_on_orthomcl_are_read_as_proteins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    async def _validate(
        _site_id: str, gene_ids: list[str], *, record_type: str
    ) -> ResolvedControls:
        asked.append(record_type)
        return ResolvedControls(valid_ids=gene_ids)

    async def _refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError

    monkeypatch.setattr(control_sets, "validate_control_ids", _validate)
    monkeypatch.setattr(control_sets, "create_control_set", _refuse)

    with pytest.raises(RuntimeError):
        await build_control_set(
            lead_run_context(site_id="orthomcl", db_session_factory=detached_session),
            name="mammal proteins",
            positive_ids=["hsap|ENSP00000216951"],
        )

    assert asked == ["sequence", "sequence"]


def test_the_phyletic_lookup_names_its_use_on_either_kind_of_site() -> None:
    doc = " ".join((inspect.getdoc(lookup_phyletic_codes) or "").split())

    assert "included_species or excluded_species" in doc
    assert "phyletic_expression" in doc
    assert "genomes" in doc
    assert "species" in doc
    assert "under the record type the site lists that search under" in doc
