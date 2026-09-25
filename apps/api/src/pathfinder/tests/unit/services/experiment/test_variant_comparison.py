"""run_variant_comparison runs each variant's search via the anonymous report
endpoint and compares result gene sets - sizes, pairwise Jaccard, and the
genes unique to each variant. No control sets, no scoring: exploratory only.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import JsonValue
from veupathdb.domain.parameters import NumberValue
from veupathdb.errors import WDKError
from veupathdb.wdk import VEuPathDBClient, WDKAnswerMeta

from pathfinder.services.experiment import variant_comparison
from pathfinder.services.experiment.variant_comparison import (
    VariantSpec,
    run_variant_comparison,
)


def _answer(gene_ids: list[str]) -> Any:
    records = []
    for gid in gene_ids:
        rec = MagicMock()
        rec.id = [MagicMock(value=gid)]
        records.append(rec)
    answer = MagicMock()
    answer.records = records
    # A real meta, so the count accessor under test actually runs.
    answer.meta = WDKAnswerMeta(
        total_count=len(gene_ids),
        display_total_count=len(gene_ids),
        view_total_count=len(gene_ids),
        display_view_total_count=len(gene_ids),
    )
    return answer


def _patch_client(
    monkeypatch: pytest.MonkeyPatch, results_by_search_value: dict[str, list[str]]
) -> None:
    async def _run_search_report(
        record_type: str,
        search_name: str,
        search_config: Any,
        report_config: Any,
        view_filters: Any,
    ) -> Any:
        # Key the mock on the fold_change param value so each variant differs.
        value = search_config.parameters.get("fold_change", "")
        return _answer(results_by_search_value[value])

    client = MagicMock()
    client.run_search_report = AsyncMock(side_effect=_run_search_report)
    monkeypatch.setattr(variant_comparison, "get_wdk_client", lambda _site: client)


@pytest.mark.asyncio
async def test_compares_sizes_overlap_and_unique_genes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(
        monkeypatch,
        {
            "2": ["g1", "g2", "g3", "g4"],
            "5": ["g3", "g4", "g5"],
        },
    )
    specs = [
        VariantSpec(
            label="2-fold",
            search_name="GenesByRNASeq",
            parameters={"fold_change": NumberValue(value=2.0)},
        ),
        VariantSpec(
            label="5-fold",
            search_name="GenesByRNASeq",
            parameters={"fold_change": NumberValue(value=5.0)},
        ),
    ]
    result = await run_variant_comparison("plasmodb", specs)

    by_label = {v.label: v for v in result.variants}
    assert by_label["2-fold"].gene_count == 4
    assert by_label["5-fold"].gene_count == 3
    # g1,g2 are unique to 2-fold; g5 unique to 5-fold.
    assert by_label["2-fold"].unique_count == 2
    assert set(by_label["2-fold"].sample_unique_genes) == {"g1", "g2"}
    assert by_label["5-fold"].unique_count == 1
    assert by_label["5-fold"].sample_unique_genes == ["g5"]

    assert len(result.overlaps) == 1
    ov = result.overlaps[0]
    assert ov.shared == 2  # g3, g4 shared
    assert ov.jaccard == round(2 / 5, 4)  # 2 shared of 5 total
    assert result.truncated is False


@pytest.mark.asyncio
async def test_one_failing_variant_does_not_crash_the_comparison(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A WDK error on ONE variant (e.g. a missing required param) must not
    blow up the whole comparison - the bad variant is reported with an
    error and the others still compare."""

    async def _run_search_report(
        record_type: str,
        search_name: str,
        search_config: Any,
        report_config: Any,
        view_filters: Any,
    ) -> Any:
        value = search_config.parameters.get("fold_change", "")
        if value == "bad":
            msg = "Parameter 'fold_change' is invalid"
            raise WDKError(msg)
        return _answer(["g1", "g2"])

    client = MagicMock()
    client.run_search_report = AsyncMock(side_effect=_run_search_report)
    monkeypatch.setattr(variant_comparison, "get_wdk_client", lambda _site: client)

    specs = [
        VariantSpec(
            label="good",
            search_name="S",
            parameters={"fold_change": NumberValue(value=2.0)},
        ),
        VariantSpec(
            label="bad",
            search_name="S",
            parameters={"fold_change": NumberValue(value=0.0)},
        ),
    ]
    # Force the second variant's wire value to "bad" via monkeypatching wire_map.
    monkeypatch.setattr(
        variant_comparison,
        "wire_map",
        lambda params: {
            "fold_change": "bad" if params["fold_change"].value == 0.0 else "2"
        },
    )

    result = await run_variant_comparison("plasmodb", specs)
    by_label = {v.label: v for v in result.variants}
    assert by_label["good"].gene_count == 2
    assert by_label["good"].error is None
    assert by_label["bad"].error == (
        "VEuPathDB service error: Parameter 'fold_change' is invalid"
    )


# A transcript search near the row cap: each gene has two transcripts, so the
# genes fit under the cap and the transcripts do not.
_GENES = 26_000
_TRANSCRIPTS_PER_GENE = 2


def _transcript_row(gene: int, transcript: int) -> JsonValue:
    return {
        "id": [
            {"name": "gene_source_id", "value": f"PF3D7_{gene:06d}"},
            {"name": "source_id", "value": f"PF3D7_{gene:06d}.{transcript}"},
            {"name": "project_id", "value": "PlasmoDB"},
        ],
        "attributes": {},
    }


class _TranscriptSite:
    """Answers a transcript report the way WDK does, one row per transcript.

    The representative transcript view filter makes it one row per gene.
    """

    def __init__(self) -> None:
        self.bodies: list[dict[str, Any]] = []

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> JsonValue:
        body = json or {}
        self.bodies.append(body)
        per_gene = 1 if "viewFilters" in body else _TRANSCRIPTS_PER_GENE
        cap = body["reportConfig"]["pagination"]["numRecords"]
        rows = [
            _transcript_row(gene, n)
            for gene in range(_GENES)
            for n in range(1, per_gene + 1)
        ][:cap]
        return {
            "records": rows,
            "meta": {
                "totalCount": _GENES * _TRANSCRIPTS_PER_GENE,
                "displayTotalCount": _GENES,
                "viewTotalCount": _GENES * per_gene,
                "displayViewTotalCount": _GENES,
                "responseCount": len(rows),
                "recordClassName": "transcript",
            },
        }


@pytest.mark.asyncio
async def test_a_transcript_search_reports_one_row_per_gene_under_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _TranscriptSite()
    client = VEuPathDBClient("https://example.invalid/service")
    monkeypatch.setattr(client, "post", site)
    monkeypatch.setattr(variant_comparison, "get_wdk_client", lambda _site: client)

    result = await run_variant_comparison(
        "plasmodb",
        [
            VariantSpec(
                label="near the cap",
                search_name="GenesByMolecularWeight",
                parameters={"min_molecular_weight": NumberValue(value=1.0)},
            )
        ],
    )

    assert site.bodies[0]["viewFilters"] == [
        {"name": "representativeTranscriptOnly", "value": {}, "disabled": False}
    ]
    assert result.truncated is False
    assert result.variants[0].gene_count == _GENES
