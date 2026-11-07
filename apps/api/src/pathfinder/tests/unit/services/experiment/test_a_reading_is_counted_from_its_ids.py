from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue
from veupathdb.domain.strategy import CombineOp
from veupathdb.wdk import WDKAnswer

from pathfinder.ai.models.mock.arc_args import SIGNALP_VERSIONS
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.strategy_specs import GENE_TYPE, SIGNAL_PEPTIDE
from pathfinder.services.experiment import reading_count, variant_comparison
from pathfinder.services.experiment.reading_count import count_reading
from pathfinder.services.experiment.variant_comparison import VariantSpec
from pathfinder.tests._support.explore_turns import SITE, RecordedReports
from pathfinder.tests._support.record_classes import recorded_searches
from pathfinder.tests.unit.domain.strategy._builders import spec_joined, spec_leaf

_ORGANISM = MultiPickValue(values=[SiteValues.for_site(SITE).organism])
_PEPTIDE = VariantSpec(
    label="peptide",
    search_name=SIGNAL_PEPTIDE,
    record_type="transcript",
    parameters={
        "organism": _ORGANISM,
        "signalp_version": SinglePickValue(value=SIGNALP_VERSIONS[0]),
    },
)
_CODING = VariantSpec(
    label="coding",
    search_name=GENE_TYPE,
    record_type="transcript",
    parameters={
        "organism": _ORGANISM,
        "geneType": MultiPickValue(values=["protein coding"]),
    },
)


_CODING_IDS = [f"PF3D7_00{n:02d}00" for n in range(10)]
_PEPTIDE_IDS = [*_CODING_IDS[:4], "PF3D7_API00100"]


def _answer(
    ids: list[str], total: int | None = None, *, transcript: str = "1"
) -> WDKAnswer:
    return WDKAnswer.model_validate(
        {
            "meta": {
                "totalCount": len(ids) if total is None else total,
                "responseCount": len(ids),
                "recordClassName": "transcript",
            },
            "records": [
                {
                    "id": [
                        {"name": "gene_source_id", "value": gene},
                        {"name": "source_id", "value": f"{gene}.{transcript}"},
                    ]
                }
                for gene in ids
            ],
        }
    )


@pytest.fixture
def reports(monkeypatch: pytest.MonkeyPatch) -> RecordedReports:
    async def _definition(site_id: str, record_type: str, search_name: str) -> object:
        del site_id, record_type
        return recorded_searches()[search_name]

    served = RecordedReports(
        answers={
            GENE_TYPE: _answer(_CODING_IDS),
            SIGNAL_PEPTIDE: _answer(_PEPTIDE_IDS),
        }
    )
    monkeypatch.setattr(reading_count, "read_search_definition", _definition)
    monkeypatch.setattr(variant_comparison, "get_wdk_client", lambda _site: served)
    return served


async def test_a_minus_counts_the_genes_of_the_left_the_right_lacks(
    reports: RecordedReports,
) -> None:
    del reports
    root = spec_joined(CombineOp.MINUS, spec_leaf("coding"), spec_leaf("peptide"))

    counted = await count_reading(SITE, [_PEPTIDE, _CODING], root)

    assert counted.gene_count == 6


async def test_the_counted_spec_states_both_searches_under_the_structure(
    reports: RecordedReports,
) -> None:
    del reports
    root = spec_joined(CombineOp.MINUS, spec_leaf("coding"), spec_leaf("peptide"))

    counted = await count_reading(SITE, [_PEPTIDE, _CODING], root)

    spec = counted.spec
    assert [(c.id, c.search_name, c.role) for c in spec.criteria] == [
        ("peptide", SIGNAL_PEPTIDE, "exclude"),
        ("coding", GENE_TYPE, "seed"),
    ]
    assert spec.ready_to_build is True
    assert counted.label.split(" MINUS ")[0].startswith("Gene Type")


async def test_a_search_that_fills_the_read_is_offered_not_counted(
    reports: RecordedReports, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(variant_comparison, "READ_CAP", 10)
    reports.answers[GENE_TYPE] = _answer(_CODING_IDS, total=50_001)

    counted = await count_reading(SITE, [_CODING], spec_leaf("coding"))

    assert (counted.gene_count, counted.not_counted) == (
        None,
        (
            "coding returns 50,001 genes, more than a reading's count reads in one "
            "read of 10 records. Narrow it, for example to one organism."
        ),
    )


async def test_a_reading_reads_every_transcript_of_its_searches(
    reports: RecordedReports,
) -> None:
    root = spec_joined(CombineOp.MINUS, spec_leaf("coding"), spec_leaf("peptide"))

    await count_reading(SITE, [_PEPTIDE, _CODING], root)

    assert reports.filters == [None, None]


async def test_a_gene_whose_transcripts_fall_apart_is_not_intersected(
    reports: RecordedReports,
) -> None:
    reports.answers[GENE_TYPE] = _answer(_CODING_IDS[:3], transcript="1")
    reports.answers[SIGNAL_PEPTIDE] = _answer(_CODING_IDS[:2], transcript="2")
    root = spec_joined(CombineOp.INTERSECT, spec_leaf("coding"), spec_leaf("peptide"))

    counted = await count_reading(SITE, [_PEPTIDE, _CODING], root)

    assert counted.gene_count == 0
