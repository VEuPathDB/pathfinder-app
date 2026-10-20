"""preview_eda_subset sends the model a bounded histogram; the figure gets every bin."""

from __future__ import annotations

import pytest
from pydantic_ai import RunContext
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.eda import EdaDistributionResponse, EdaStudyDetail

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis
from pathfinder.ai.tools.standalone._eda_models import EdaSubsetPreviewResult
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.services.eda import binding
from pathfinder.services.eda.authoring import SubsetPreview
from pathfinder.services.eda.gene_subset import GeneCount
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    SPECIES_VARIABLE,
    phenotype_study,
    read_analysis_detail,
    recorded_entity_counts,
)
from pathfinder.tests._support.eda_step_doubles import PHENOTYPE_GENES
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    fixture,
)
from pathfinder.tests._support.tool_returns import returned, wire_size

_ONE_BIN_PER_GENE = 8_776
_PREVIEW_CEILING = 4_000


async def _bound(_ctx: object) -> ConversationAnalysisView:
    return ConversationAnalysisView(
        site_id="plasmodb",
        dataset_id=PHENOTYPE_DATASET,
        analysis_id=ANALYSIS_ID,
        revision=1,
    )


async def _record_preview(*, conversation_id: object) -> None:
    del conversation_id


async def _genes_counted(
    _site: str, *, study: EdaStudyDetail, entity_id: str, filters: object
) -> GeneCount:
    del study, entity_id, filters
    return PHENOTYPE_GENES


def _preview_of(histogram: list[dict[str, object]]) -> SubsetPreview:
    payload = fixture("distribution_categorical")
    payload["histogram"] = histogram
    return SubsetPreview(
        entity_id=PHENOTYPE_ENTITY,
        entity_display_name="Gene Phenotype Data",
        entity_display_name_plural="Gene Phenotype Data",
        count=4279,
        unfiltered_count=4279,
        distribution=EdaDistributionResponse.model_validate(payload),
    )


def _wire(monkeypatch: pytest.MonkeyPatch, preview: SubsetPreview) -> None:
    async def previewed(_site: str, **_kwargs: object) -> SubsetPreview:
        return preview

    monkeypatch.setattr(binding, "subset_entity_counts", recorded_entity_counts)
    monkeypatch.setattr(eda_analysis, "record_subset_preview", _record_preview)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    monkeypatch.setattr(eda_analysis, "read_analysis", read_analysis_detail)
    monkeypatch.setattr(eda_analysis, "preview_subset", previewed)
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", phenotype_study)
    monkeypatch.setattr(eda_analysis, "gene_count", _genes_counted)


def _gene_bins() -> list[dict[str, object]]:
    return [
        {"value": 12, "binStart": label, "binEnd": label, "binLabel": label}
        for label in (f"TGME49_{200000 + i}" for i in range(_ONE_BIN_PER_GENE))
    ]


async def test_a_preview_with_thousands_of_bins_sends_the_first_and_their_total(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, _preview_of(_gene_bins()))
    answer = await eda_analysis.preview_eda_subset(
        lead_ctx,
        entity_id=PHENOTYPE_ENTITY,
        distribution_variable_id=SPECIES_VARIABLE,
    )
    result = returned(answer, EdaSubsetPreviewResult)
    figure = [
        chunk.data["distribution"]["labels"]
        for chunk in answer.metadata
        if isinstance(chunk, DataChunk) and chunk.type == "data-eda.subset-preview"
    ]

    assert result.labels == [f"TGME49_{200000 + i}" for i in range(40)]
    assert result.values == [12.0] * 40
    assert result.bin_total == _ONE_BIN_PER_GENE
    assert result.bins_note == (
        f"{_ONE_BIN_PER_GENE:,} bins in all; the first 40 are shown here. The "
        "figure shows every bin."
    )
    assert [len(labels) for labels in figure] == [_ONE_BIN_PER_GENE]
    assert wire_size(answer, "preview_eda_subset") < _PREVIEW_CEILING


async def test_a_preview_with_few_bins_sends_them_all_and_no_note(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, _preview_of(fixture("distribution_categorical")["histogram"]))
    answer = await eda_analysis.preview_eda_subset(
        lead_ctx,
        entity_id=PHENOTYPE_ENTITY,
        distribution_variable_id=SPECIES_VARIABLE,
    )
    result = returned(answer, EdaSubsetPreviewResult)
    assert result.labels == ["P. berghei", "P. falciparum", "P. yoelii"]
    assert (result.bin_total, result.bins_note) == (3, None)
