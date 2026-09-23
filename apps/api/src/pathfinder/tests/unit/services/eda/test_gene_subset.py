"""gene_subset names the entities a subset filters against the gene entity."""

from __future__ import annotations

from veupathdb.eda import EdaStudyDetailResponse

from pathfinder.services.eda.gene_subset import gene_subset
from pathfinder.tests._support.eda_wire import fixture
from pathfinder.tests.unit.ai.tools._eda_step_doubles import (
    gene_filter,
    sample_filter,
)

_STUDY = EdaStudyDetailResponse.model_validate(fixture("study_detail_de")).study


def test_filters_on_samples_name_the_sample_entity_once_and_no_gene() -> None:
    subset = gene_subset(_STUDY, [sample_filter(), sample_filter()])

    assert subset.filters_genes is False
    assert subset.filters_clause() == "2 filters on Sample"
    assert subset.gene_entity_clause() == "pfal3D7 htseq counts (ENT_fd574cd6)"


def test_a_filter_on_the_gene_entity_filters_genes() -> None:
    subset = gene_subset(_STUDY, [sample_filter(), gene_filter()])

    assert subset.filters_genes is True
    assert subset.filters_clause() == "2 filters on Sample, pfal3D7 htseq counts"


def test_no_filter_is_stated_as_no_filter() -> None:
    subset = gene_subset(_STUDY, [])

    assert subset.filters_genes is False
    assert subset.filters_clause() == "no filter"
