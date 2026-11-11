from __future__ import annotations

from collections.abc import Sequence

import pytest
from veupathdb.eda import EdaDistributionResponse, EdaFilter, EdaNumberRangeFilter
from veupathdb.testing.eda_fixtures import FIXTURE_DIR, recorded_distribution

from pathfinder.domain.eda_cut import ClassCount
from pathfinder.domain.strategy.question_options import TailRule
from pathfinder.services.eda import cut_offer
from pathfinder.services.eda.authoring import SubsetPreview
from pathfinder.services.eda.cut_offer import (
    OfferedCut,
    class_counts_of,
    counted_noun,
    study_cut_question,
    tail_edges_of,
)
from pathfinder.tests._support.eda_doubles import SPECIES_VARIABLE, study_of
from pathfinder.tests._support.eda_wire import PHENOTYPE_ENTITY
from pathfinder.tests._support.qa_recording import qa_recording

# The continuous distribution the client's knowledge bundle records for a
# five-unit binSpec: half-open bins whose edges travel as strings.
_CONTINUOUS = {
    "histogram": [
        {"value": 13, "binStart": "0.0", "binEnd": "5.0", "binLabel": "[0.0,5.0)"},
        {"value": 3254, "binStart": "5.0", "binEnd": "10.0", "binLabel": "[5.0,10.0)"},
        {
            "value": 31990,
            "binStart": "10.0",
            "binEnd": "15.0",
            "binLabel": "[10.0,15.0)",
        },
        {
            "value": 1313,
            "binStart": "15.0",
            "binEnd": "20.0",
            "binLabel": "[15.0,20.0)",
        },
        {"value": 0, "binStart": "20.0", "binEnd": "25.0", "binLabel": "[20.0,25.0)"},
    ],
    "statistics": {
        "subsetSize": 48721,
        "subsetMin": 3.0,
        "subsetMax": 18.9,
        "numVarValues": 36570,
        "numDistinctValues": 174,
        "numDistinctEntityRecords": 36570,
        "numMissingCases": 12151,
    },
}


def test_each_class_carries_its_count_from_the_categorical_distribution() -> None:
    categorical = recorded_distribution(
        qa_recording(FIXTURE_DIR / "distribution_categorical.json").stem
    )
    assert class_counts_of(
        categorical,
        entity_id=PHENOTYPE_ENTITY,
        variable_id=SPECIES_VARIABLE,
        variable_name="Species",
    ) == [
        ClassCount(
            entity_id=PHENOTYPE_ENTITY,
            variable_id=SPECIES_VARIABLE,
            variable_name="Species",
            value=value,
            count=count,
        )
        for value, count in (
            ("P. berghei", 4011),
            ("P. falciparum", 4130),
            ("P. yoelii", 268),
        )
    ]


def test_the_tails_read_the_wire_bins_at_their_edges() -> None:
    distribution = EdaDistributionResponse.model_validate(_CONTINUOUS)
    assert [
        (e.rule, e.bound, e.count, e.total) for e in tail_edges_of(distribution)
    ] == [
        (TailRule(end="low", percent=5), 10.0, 3267, 36570),
        (TailRule(end="low", percent=10), 15.0, 35257, 36570),
        (TailRule(end="high", percent=5), 10.0, 33303, 36570),
    ]


def test_no_distribution_offers_no_tail() -> None:
    assert tail_edges_of(None) == []


def test_the_gene_entity_counts_genes_and_another_its_own_plural() -> None:
    gene = study_of(
        [
            {
                "id": "VEUPATHDB_GENE_ID",
                "type": "string",
                "displayName": "Gene",
                "dataShape": "categorical",
            }
        ],
        entity_id=PHENOTYPE_ENTITY,
    )
    sample = study_of([], entity_id="Samples")
    assert (counted_noun(gene, PHENOTYPE_ENTITY), counted_noun(sample, "Samples")) == (
        "genes",
        "Samples",
    )


_SCORE = "VAR_score"
_SELECTED_BY_THE_FILTER = {(0.0, 10.0): 3301, (0.0, 15.0): 35290, (10.0, 25.0): 33344}


def _range(each: EdaFilter) -> tuple[float, float]:
    match each:
        case EdaNumberRangeFilter(min=low, max=high):
            return (low, high)
        case _:
            raise AssertionError(each)


async def test_each_tail_counts_what_its_own_filter_selects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def preview_subset(
        site_id: str,
        *,
        dataset_id: str,
        entity_id: str,
        filters: Sequence[EdaFilter],
        distribution_variable_id: str | None = None,
    ) -> SubsetPreview:
        del site_id, dataset_id, distribution_variable_id
        ranges = [_range(f) for f in filters]
        return SubsetPreview(
            entity_id=entity_id,
            entity_display_name="Gene",
            entity_display_name_plural="Genes",
            count=sum(_SELECTED_BY_THE_FILTER[r] for r in ranges),
            unfiltered_count=48721,
            distribution=None
            if ranges
            else EdaDistributionResponse.model_validate(_CONTINUOUS),
        )

    monkeypatch.setattr(cut_offer, "preview_subset", preview_subset)
    study = study_of(
        [
            {
                "id": "VEUPATHDB_GENE_ID",
                "type": "string",
                "displayName": "Gene",
                "dataShape": "categorical",
            }
        ],
        entity_id=PHENOTYPE_ENTITY,
    )

    question = await study_cut_question(
        "plasmodb",
        dataset_id="DS_phenotype",
        study=study,
        cut=OfferedCut(
            entity_id=PHENOTYPE_ENTITY,
            variable_id=_SCORE,
            variable_name="Fitness score",
            numeric=True,
            classes=[],
        ),
    )

    assert [option.label for option in question.options] == [
        "Lowest 9.0% of Fitness score: at most 10 (3301 genes)",
        "Lowest 96.5% of Fitness score: at most 15 (35290 genes)",
        "Highest 91.2% of Fitness score: at least 10 (33344 genes)",
    ]


async def test_each_recount_stays_inside_the_declared_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[float, float]] = []

    async def preview_subset(
        site_id: str,
        *,
        dataset_id: str,
        entity_id: str,
        filters: Sequence[EdaFilter],
        distribution_variable_id: str | None = None,
    ) -> SubsetPreview:
        del site_id, dataset_id, distribution_variable_id
        sent.extend(_range(f) for f in filters)
        return SubsetPreview(
            entity_id=entity_id,
            entity_display_name="Gene",
            entity_display_name_plural="Genes",
            count=1,
            unfiltered_count=48721,
            distribution=None
            if filters
            else EdaDistributionResponse.model_validate(_CONTINUOUS),
        )

    monkeypatch.setattr(cut_offer, "preview_subset", preview_subset)
    study = study_of(
        [
            {
                "id": _SCORE,
                "type": "number",
                "displayName": "Fitness score",
                "dataShape": "continuous",
                "distributionDefaults": {
                    "rangeMin": 3.0,
                    "rangeMax": 18.9,
                    "binWidth": 5,
                },
            }
        ],
        entity_id=PHENOTYPE_ENTITY,
    )

    await study_cut_question(
        "plasmodb",
        dataset_id="DS_phenotype",
        study=study,
        cut=OfferedCut(
            entity_id=PHENOTYPE_ENTITY,
            variable_id=_SCORE,
            variable_name="Fitness score",
            numeric=True,
            classes=[],
        ),
    )

    assert sent == [(3.0, 10.0), (3.0, 15.0), (10.0, 18.9)]
