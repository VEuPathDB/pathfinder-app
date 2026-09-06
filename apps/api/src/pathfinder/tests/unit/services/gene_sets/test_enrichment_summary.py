"""The gene set enrichment summary counts terms that survive multiple testing.

A raw p-value below 0.05 is not a finding once hundreds of GO terms are tested;
the FDR the analysis already reports is what the count must read.
"""

from __future__ import annotations

import pytest
from assistant_core.platform.types import JSONArray, JSONObject
from pydantic import TypeAdapter
from veupathdb_mcp.wdk.enrichment.types import (
    EnrichmentAnalysisType,
    EnrichmentResult,
    EnrichmentTerm,
)

from pathfinder.services.export.service import ExportResult
from pathfinder.services.gene_sets import enrichment
from pathfinder.services.gene_sets.enrichment import run_enrichment_for_gene_set
from pathfinder.services.gene_sets.types import GeneSet

_ARRAY: TypeAdapter[JSONArray] = TypeAdapter(JSONArray)
_OBJECT: TypeAdapter[JSONObject] = TypeAdapter(JSONObject)


def _term(term_id: str, p_value: float, fdr: float | None) -> EnrichmentTerm:
    return EnrichmentTerm(
        term_id=term_id,
        term_name=f"term {term_id}",
        gene_count=5,
        background_count=100,
        fold_enrichment=3.0,
        odds_ratio=3.0,
        p_value=p_value,
        fdr=fdr,
        bonferroni=fdr,
        genes=["PF3D7_0100100"],
    )


_RESULTS = [
    EnrichmentResult(
        analysis_type="go_process",
        terms=[
            _term("GO:0006468", p_value=0.001, fdr=0.01),
            _term("GO:0016311", p_value=0.01, fdr=0.20),
            _term("GO:0004672", p_value=0.03, fdr=0.04),
            _term("GO:0000001", p_value=0.001, fdr=None),
        ],
        total_genes_analyzed=42,
    ),
]


class _StubEnrichmentService:
    """Stands in for the WDK round trip."""

    async def run_batch(
        self, **kwargs: object
    ) -> tuple[list[EnrichmentResult], list[str]]:
        del kwargs
        return _RESULTS, []


class _StubExportService:
    """Returns fixed export metadata without touching storage."""

    async def export_enrichment(
        self, results: list[EnrichmentResult], name: str
    ) -> ExportResult:
        del results
        return self._result(name, "csv", "text/csv")

    async def export_enrichment_tsv(
        self, results: list[EnrichmentResult], name: str
    ) -> ExportResult:
        del results
        return self._result(name, "tsv", "text/tab-separated-values")

    async def export_enrichment_json(
        self, results: list[EnrichmentResult], name: str
    ) -> ExportResult:
        del results
        return self._result(name, "json", "application/json")

    def _result(self, name: str, suffix: str, content_type: str) -> ExportResult:
        return ExportResult(
            export_id=f"export-{suffix}",
            filename=f"{name}.{suffix}",
            content_type=content_type,
            url=f"/api/v1/exports/export-{suffix}",
            size_bytes=128,
            expires_in_seconds=3600,
        )


def _stub_services(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(enrichment, "EnrichmentService", _StubEnrichmentService)
    monkeypatch.setattr(enrichment, "get_export_service", _StubExportService)


def _gene_set() -> GeneSet:
    return GeneSet(
        id="gs-1",
        name="kinase panel",
        site_id="plasmodb",
        gene_ids=["PF3D7_0100100", "PF3D7_0100200"],
        source="paste",
        wdk_step_id=5,
        record_type="transcript",
    )


_TYPES: list[EnrichmentAnalysisType] = ["go_process"]


async def test_only_terms_that_pass_fdr_are_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_services(monkeypatch)

    summary = await run_enrichment_for_gene_set(_gene_set(), _TYPES)

    assert summary["totalSignificantTerms"] == 2


async def test_a_term_with_no_computable_fdr_is_not_significant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_services(monkeypatch)

    summary = await run_enrichment_for_gene_set(_gene_set(), _TYPES)
    results = _ARRAY.validate_python(summary["enrichmentResults"])
    terms = _ARRAY.validate_python(_OBJECT.validate_python(results[0])["terms"])
    unscored = _OBJECT.validate_python(terms[3])

    assert unscored["fdr"] is None
    assert summary["totalSignificantTerms"] == 2


async def test_the_summary_keeps_its_wire_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_services(monkeypatch)

    summary = await run_enrichment_for_gene_set(_gene_set(), _TYPES)

    assert summary["analysisTypesRun"] == ["go_process"]
    results = _ARRAY.validate_python(summary["enrichmentResults"])
    first = _OBJECT.validate_python(results[0])
    assert first["analysisType"] == "go_process"
    assert len(_ARRAY.validate_python(first["terms"])) == 4
    downloads = _OBJECT.validate_python(summary["downloads"])
    assert downloads["csv"] == "/api/v1/exports/export-csv"
    assert downloads["expiresInSeconds"] == 3600
