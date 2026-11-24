from __future__ import annotations

from typing import Any

import pytest
from pydantic import JsonValue, ValidationError
from veupathdb.domain.parameters import StringValue
from veupathdb.wdk import VEuPathDBClient

from strategist.services.experiment import variant_comparison
from strategist.services.experiment.variant_comparison import (
    PairwiseOverlap,
    VariantComparison,
    VariantResult,
    VariantSpec,
    run_variant_comparison,
)

# The site holds g1 to g6 for the wide variant and g3, g5, g7 for the narrow one.
_HELD = {"wide": [f"g{n}" for n in range(1, 7)], "narrow": ["g3", "g5", "g7"]}


class _PagedSite:
    """Answers each report with the first ``numRecords`` ids and the full total."""

    async def __call__(
        self, path: str, json: dict[str, Any] | None = None, **_: object
    ) -> JsonValue:
        body = json or {}
        held = _HELD[body["searchConfig"]["parameters"]["text_expression"]]
        rows: list[JsonValue] = [
            {"id": [{"name": "gene_source_id", "value": gene}], "attributes": {}}
            for gene in held[: body["reportConfig"]["pagination"]["numRecords"]]
        ]
        return {
            "records": rows,
            "meta": {
                "totalCount": len(held),
                "displayTotalCount": len(held),
                "viewTotalCount": len(held),
                "displayViewTotalCount": len(held),
                "responseCount": len(rows),
                "recordClassName": "transcript",
            },
        }


@pytest.mark.asyncio
async def test_a_set_read_to_the_cap_reports_no_count_it_cannot_give(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = VEuPathDBClient("https://example.invalid/service")
    monkeypatch.setattr(client, "post", _PagedSite())
    monkeypatch.setattr(variant_comparison, "get_wdk_client", lambda _site: client)
    monkeypatch.setattr(variant_comparison, "READ_CAP", 4)
    specs = [
        VariantSpec(
            label=label,
            search_name="GenesByText",
            record_type="transcript",
            parameters={"text_expression": StringValue(value=label)},
        )
        for label in ("wide", "narrow")
    ]

    result = await run_variant_comparison("plasmodb", specs)

    wide, narrow = result.variants
    [overlap] = result.overlaps
    assert result.read_cap == 4
    assert (wide.gene_count, wide.read_to_cap, wide.unique_count) == (6, True, 3)
    assert wide.unique_at_least is True
    assert [g.gene_id for g in wide.sample_unique_genes] == ["g1", "g2", "g4"]
    assert (narrow.gene_count, narrow.read_to_cap, narrow.unique_count) == (
        3,
        False,
        None,
    )
    assert (narrow.unique_at_least, narrow.sample_unique_genes) == (False, [])
    assert (overlap.shared, overlap.shared_at_least, overlap.jaccard) == (
        1,
        True,
        None,
    )


def test_an_overlap_with_a_partial_read_holds_no_jaccard() -> None:
    with pytest.raises(ValidationError, match=r"jaccard 0\.5"):
        PairwiseOverlap(
            a="wide", b="narrow", shared=1, shared_at_least=True, jaccard=0.5
        )


def test_no_variant_names_unique_genes_beside_a_partial_read() -> None:
    def _variant(label: str, *, read_to_cap: bool) -> VariantResult:
        return VariantResult(
            label=label,
            search_name="GenesByText",
            gene_count=6,
            read_to_cap=read_to_cap,
            unique_count=2,
            sample_unique_genes=[],
        )

    with pytest.raises(ValidationError, match="'narrow' names unique genes"):
        VariantComparison(
            variants=[
                _variant("wide", read_to_cap=True),
                _variant("narrow", read_to_cap=False),
            ],
            overlaps=[],
        )
