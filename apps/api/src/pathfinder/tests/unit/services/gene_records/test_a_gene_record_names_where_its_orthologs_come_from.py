from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from veupathdb.wdk import (
    AiExpressionStatus,
    StrategyAPI,
    WDKRecordInstance,
    WDKRecordType,
)
from veupathdb_mcp.wdk import GeneExpressionSummary

from pathfinder.services.gene_records import read
from pathfinder.services.gene_records.read import read_the_gene_record
from pathfinder.tests._support.qa_recording import qa_recording

_RECORDED = Path(__file__).resolve().parents[3] / "fixtures" / "wdk"
_GENE_ATTRIBUTES = ("organism", "product", "name", "orthomcl_name", "project_id")


class _OneGene(StrategyAPI):
    def __init__(self, record: WDKRecordInstance, *, declares: tuple[str, ...]) -> None:
        self._record = record
        self._declares = declares
        self.asked_attributes: list[str] = []

    async def get_record_type_info(self, record_type: str) -> WDKRecordType:
        assert record_type == "gene"
        return WDKRecordType.model_validate(
            {
                "urlSegment": "gene",
                "primaryKeyColumnRefs": ["source_id", "project_id"],
                "attributes": [
                    {"name": name, "columnDataType": "STRING"}
                    for name in self._declares
                ],
            }
        )

    async def get_single_record(
        self,
        record_type: str,
        primary_key: list[dict[str, str]],
        *,
        attributes: list[str] | None = None,
        tables: list[str] | None = None,
    ) -> WDKRecordInstance:
        del record_type, primary_key, tables
        self.asked_attributes = list(attributes or [])
        return self._record


@pytest.fixture(autouse=True)
def _no_expression(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(read, "_gene_record_types", {})

    async def _none(site_id: str, gene_id: str) -> GeneExpressionSummary:
        return GeneExpressionSummary(
            site_id=site_id,
            gene_id=gene_id,
            result_status=AiExpressionStatus.MISSING,
            unavailable_reason="no summary",
        )

    monkeypatch.setattr(read, "get_gene_expression_summary", _none)


def _recorded_piga() -> WDKRecordInstance:
    body = json.loads(
        qa_recording(_RECORDED / "gene_record_PF3D7_1032400.json").read_text()
    )
    return WDKRecordInstance.model_validate(body)


def _portal_record(attributes: Mapping[str, str]) -> WDKRecordInstance:
    return WDKRecordInstance.model_validate(
        {
            "displayName": "PBANKA_1033800",
            "recordClassName": "GeneRecordClasses.GeneRecordClass",
            "id": [
                {"name": "source_id", "value": "PBANKA_1033800"},
                {"name": "project_id", "value": "UniDB"},
            ],
            "attributes": dict(attributes),
            "tables": {},
        }
    )


async def test_a_plasmodb_record_names_the_genomes_its_table_lists_and_its_group() -> (
    None
):
    api = _OneGene(_recorded_piga(), declares=_GENE_ATTRIBUTES)

    found = await read_the_gene_record(api, "plasmodb", "PF3D7_1032400")

    assert "orthomcl_name" in api.asked_attributes
    assert (found.ortholog_group, found.ortholog_site) == ("OG8_0001100", "PlasmoDB")
    assert found.ortholog_scope == (
        "The Orthologs table lists only genomes PlasmoDB holds. Orthology to a "
        "genome on another site is the gene's OrthoMCL group OG8_0001100 and "
        "membership in an ortholog-pattern step."
    )


async def test_a_portal_record_names_the_site_that_holds_its_gene() -> None:
    record = _portal_record(
        {
            "organism": "P. berghei ANKA",
            "product": "conserved protein, unknown function",
            "orthomcl_name": "OG8_0007998",
            "project_id": "PlasmoDB",
        }
    )
    api = _OneGene(record, declares=_GENE_ATTRIBUTES)

    found = await read_the_gene_record(api, "veupathdb", "PBANKA_1033800")

    assert found.ortholog_site == "PlasmoDB"
    assert found.ortholog_scope.startswith(
        "The Orthologs table lists only genomes PlasmoDB holds."
    )
    assert "OrthoMCL group OG8_0007998" in found.ortholog_scope


async def test_a_record_without_a_group_still_names_where_orthology_is_read() -> None:
    record = _portal_record({"organism": "P. berghei ANKA", "project_id": "PlasmoDB"})
    api = _OneGene(record, declares=("organism", "project_id"))

    found = await read_the_gene_record(api, "veupathdb", "PBANKA_1033800")

    assert found.ortholog_group is None
    assert found.ortholog_scope == (
        "The Orthologs table lists only genomes PlasmoDB holds. Orthology to a "
        "genome on another site is the gene's OrthoMCL group and membership in "
        "an ortholog-pattern step."
    )


async def test_a_portal_record_of_no_configured_site_names_the_gene_s_own_site() -> (
    None
):
    api = _OneGene(_portal_record({"organism": "P. berghei ANKA"}), declares=())

    found = await read_the_gene_record(api, "veupathdb", "PBANKA_1033800")

    assert found.ortholog_site is None
    assert found.ortholog_scope.startswith(
        "The Orthologs table lists only genomes the gene's own site holds."
    )
