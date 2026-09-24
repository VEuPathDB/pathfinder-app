"""preview_eda_subset reports both counts and narrates what the numbers mean."""

from __future__ import annotations

from dataclasses import replace
from uuid import UUID

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.eda import (
    EdaAnalysisDetail,
    EdaDistributionResponse,
    EdaFilter,
    EdaStringSetFilter,
    EdaStudyDetail,
)

from pathfinder.ai.lead.intent_gate import unmet_preconditions
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis
from pathfinder.ai.tools.standalone._eda_models import EdaSubsetPreviewResult
from pathfinder.domain.eda_parts import EdaAnalysisState
from pathfinder.services.eda import binding
from pathfinder.services.eda.authoring import SubsetPreview
from pathfinder.services.eda.binding import ConversationAnalysisView
from pathfinder.services.eda.gene_subset import GeneCount
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    SPECIES_VARIABLE,
    RevisionCounter,
    phenotype_study,
    read_analysis_detail,
    recorded_entity_counts,
)
from pathfinder.tests._support.eda_step_doubles import (
    COUNTS_ENTITY,
    DE_GENES,
    PHENOTYPE_GENES,
    SAMPLE_ENTITY,
    binding_of,
    de_analysis,
    de_study,
    gene_filter,
    sample_filter,
)
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    PHENOTYPE_STUDY,
    fixture,
)
from pathfinder.tests._support.tool_returns import returned


@pytest.fixture(autouse=True)
def revisions(monkeypatch: pytest.MonkeyPatch) -> RevisionCounter:
    counter = RevisionCounter()
    monkeypatch.setattr(binding, "bump_analysis_revision", counter.bump)
    return counter


@pytest.fixture(autouse=True)
def entity_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tools are read through their chunks, not through the count wire."""
    monkeypatch.setattr(binding, "subset_entity_counts", recorded_entity_counts)


async def _bound(_ctx: object) -> ConversationAnalysisView:
    return ConversationAnalysisView(
        site_id="plasmodb",
        dataset_id=PHENOTYPE_DATASET,
        analysis_id=ANALYSIS_ID,
        revision=1,
    )


async def _unbound(_ctx: object) -> ConversationAnalysisView | None:
    return None


def _preview(
    *, count: int, distribution: EdaDistributionResponse | None
) -> SubsetPreview:
    return SubsetPreview(
        entity_id=PHENOTYPE_ENTITY,
        entity_display_name="Gene Phenotype Data",
        entity_display_name_plural="Gene Phenotype Data",
        count=count,
        unfiltered_count=4279,
        distribution=distribution,
    )


def _categorical() -> EdaDistributionResponse:
    return EdaDistributionResponse.model_validate(fixture("distribution_categorical"))


async def _preview_ok(_site: str, **_kwargs: object) -> SubsetPreview:
    return _preview(count=4011, distribution=_categorical())


async def _preview_zero(_site: str, **_kwargs: object) -> SubsetPreview:
    return _preview(count=0, distribution=None)


async def _preview_whole_entity(_site: str, **_kwargs: object) -> SubsetPreview:
    return _preview(count=4279, distribution=None)


async def _preview_with_missing(_site: str, **_kwargs: object) -> SubsetPreview:
    payload = fixture("distribution_categorical")
    payload["statistics"]["numMissingCases"] = 12
    return _preview(
        count=4011, distribution=EdaDistributionResponse.model_validate(payload)
    )


async def _record_preview(*, conversation_id: object) -> None:
    del conversation_id


async def _genes_counted(
    _site: str, *, study: EdaStudyDetail, entity_id: str, filters: object
) -> GeneCount:
    assert (study.id, entity_id) == (PHENOTYPE_STUDY, PHENOTYPE_ENTITY)
    del filters
    return PHENOTYPE_GENES


def _wire(monkeypatch: pytest.MonkeyPatch, preview: object) -> None:
    monkeypatch.setattr(eda_analysis, "record_subset_preview", _record_preview)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    monkeypatch.setattr(eda_analysis, "read_analysis", read_analysis_detail)
    monkeypatch.setattr(eda_analysis, "preview_subset", preview)
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", phenotype_study)
    monkeypatch.setattr(eda_analysis, "gene_count", _genes_counted)


def _captions(metadata: object) -> list[str]:
    chunks = metadata if isinstance(metadata, list) else []
    return [
        chunk.data["caption"]
        for chunk in chunks
        if isinstance(chunk, DataChunk) and chunk.type == "data-eda.subset-preview"
    ]


async def test_preview_eda_subset_reports_both_counts_and_emits_the_part(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, _preview_ok)
    answer = await eda_analysis.preview_eda_subset(
        lead_ctx,
        entity_id=PHENOTYPE_ENTITY,
        distribution_variable_id=SPECIES_VARIABLE,
    )
    result = returned(answer, EdaSubsetPreviewResult)
    assert result.count == 4011
    assert result.unfiltered_count == 4279
    assert result.labels == [
        "P. berghei",
        "P. falciparum",
        "P. yoelii",
    ]
    assert result.values == [4011.0, 4130.0, 268.0]
    assert [c.type for c in answer.metadata] == ["data-eda.subset-preview"]


async def test_a_preview_puts_the_model_s_caption_on_the_part(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The figure reads the model's sentence, so the tool must carry it."""
    _wire(monkeypatch, _preview_ok)
    answer = await eda_analysis.preview_eda_subset(
        lead_ctx,
        entity_id=PHENOTYPE_ENTITY,
        distribution_variable_id=SPECIES_VARIABLE,
        caption="Species of the phenotyped genes the filters keep",
    )
    assert _captions(answer.metadata) == [
        "Species of the phenotyped genes the filters keep"
    ]


async def test_a_preview_with_no_caption_leaves_the_part_s_caption_empty(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, _preview_ok)
    answer = await eda_analysis.preview_eda_subset(lead_ctx, entity_id=PHENOTYPE_ENTITY)
    assert _captions(answer.metadata) == [""]


async def test_a_preview_of_zero_says_which_filter_emptied_the_subset(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """Zero is a real answer and the model must not silently narrate a result."""
    _wire(monkeypatch, _preview_zero)
    answer = await eda_analysis.preview_eda_subset(lead_ctx, entity_id=PHENOTYPE_ENTITY)
    result = returned(answer, EdaSubsetPreviewResult)
    assert result.count == 0
    assert "selects no records" in result.guidance


async def test_a_preview_of_zero_reports_its_summary_as_empty(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The line carries the zero and the status says empty, never ok."""
    _wire(monkeypatch, _preview_zero)
    ctx = replace(lead_ctx, tool_call_id="call_1")
    answer = await eda_analysis.preview_eda_subset(ctx, entity_id=PHENOTYPE_ENTITY)
    summaries = [
        chunk.data
        for chunk in answer.metadata
        if isinstance(chunk, DataChunk) and chunk.type == "data-tool-summary"
    ]
    assert summaries == [
        {
            "toolCallId": "call_1",
            "summary": "0 of 4,279 Gene Phenotype Data",
            "status": "empty",
        }
    ]


async def test_a_subset_that_narrows_nothing_says_so(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A filter on a child entity can leave the parent entity whole."""
    _wire(monkeypatch, _preview_whole_entity)
    answer = await eda_analysis.preview_eda_subset(lead_ctx, entity_id=PHENOTYPE_ENTITY)
    result = returned(answer, EdaSubsetPreviewResult)
    assert "narrow nothing here" in result.guidance


async def test_a_multi_valued_distribution_warns_that_the_values_do_not_partition(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, _preview_ok)
    answer = await eda_analysis.preview_eda_subset(
        lead_ctx,
        entity_id=PHENOTYPE_ENTITY,
        distribution_variable_id=SPECIES_VARIABLE,
    )
    result = returned(answer, EdaSubsetPreviewResult)
    assert result.is_multi_valued is True
    assert "several values per record" in result.guidance


async def test_a_preview_reports_the_records_with_no_value_for_the_variable(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, _preview_with_missing)
    answer = await eda_analysis.preview_eda_subset(
        lead_ctx,
        entity_id=PHENOTYPE_ENTITY,
        distribution_variable_id=SPECIES_VARIABLE,
    )
    result = returned(answer, EdaSubsetPreviewResult)
    assert result.num_missing_cases == 12
    assert "12 records" in result.guidance


async def test_a_preview_with_no_open_analysis_raises_a_model_retry(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    monkeypatch.setattr(eda_analysis, "bound_analysis", _unbound)
    with pytest.raises(ModelRetry) as excinfo:
        await eda_analysis.preview_eda_subset(lead_ctx, entity_id=PHENOTYPE_ENTITY)
    assert "open_eda_analysis" in str(excinfo.value)


async def test_a_preview_records_the_count_on_the_thread_s_analysis(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The count belongs to the analysis, so a later message can export it."""
    counted: list[UUID | None] = []

    async def _record(*, conversation_id: UUID | None) -> None:
        counted.append(conversation_id)

    _wire(monkeypatch, _preview_ok)
    monkeypatch.setattr(eda_analysis, "record_subset_preview", _record)

    await eda_analysis.preview_eda_subset(lead_ctx, entity_id=PHENOTYPE_ENTITY)

    assert counted == [lead_ctx.deps.state.conversation_id]
    open_analysis = lead_ctx.deps.state.domain.open_eda_analysis
    assert open_analysis is not None
    assert open_analysis.analysis_id == ANALYSIS_ID
    assert open_analysis.subset_previewed


async def _applied(
    _site: str,
    *,
    conversation_id: UUID,
    analysis_id: str,
    dataset_id: str,
    filters: object,
) -> EdaAnalysisState:
    del conversation_id, analysis_id, filters
    return EdaAnalysisState(
        site_id="plasmodb",
        dataset_id=dataset_id,
        study_id=PHENOTYPE_STUDY,
        analysis_id=ANALYSIS_ID,
        revision=2,
        study_display_name="Rodent malaria phenotypes",
        display_name="berghei subset",
        num_filters=1,
        num_computations=0,
        filters=[],
        filter_summaries=["Species is one of P. berghei"],
        entity_counts=[],
        can_export_rows=False,
    )


async def test_a_count_after_a_filter_change_opens_the_export_again(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The gate follows the subset: counted, changed, counted again."""
    _wire(monkeypatch, _preview_ok)
    monkeypatch.setattr(eda_analysis, "apply_filters", _applied)

    await eda_analysis.preview_eda_subset(lead_ctx, entity_id=PHENOTYPE_ENTITY)
    assert "create_eda_step" not in unmet_preconditions(lead_ctx.deps)

    await eda_analysis.set_eda_filters(
        lead_ctx,
        dataset_id=PHENOTYPE_DATASET,
        filters=[
            EdaStringSetFilter(
                entity_id=PHENOTYPE_ENTITY,
                variable_id=SPECIES_VARIABLE,
                string_set=["P. berghei"],
            )
        ],
    )
    assert "create_eda_step" in unmet_preconditions(lead_ctx.deps)

    await eda_analysis.preview_eda_subset(lead_ctx, entity_id=PHENOTYPE_ENTITY)
    assert "create_eda_step" not in unmet_preconditions(lead_ctx.deps)


async def test_a_preview_of_the_gene_entity_states_its_genes_beside_its_rows(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """4,011 phenotype rows name 5,595 genes, so a row count is not a gene count."""
    _wire(monkeypatch, _preview_ok)

    answer = await eda_analysis.preview_eda_subset(lead_ctx, entity_id=PHENOTYPE_ENTITY)
    result = returned(answer, EdaSubsetPreviewResult)

    assert result.guidance == (
        "Genes this subset selects: 5,595 of 5,803, counted as distinct gene ids "
        "on Gene Phenotype Data. State this gene count, not a row count, as the "
        "genes a step would export; the step's own count comes from the site "
        "once it runs."
    )


def _wire_de(
    monkeypatch: pytest.MonkeyPatch,
    *,
    filters: list[EdaFilter],
    counted: SubsetPreview,
) -> list[str]:
    """The RNA-Seq study, one analysis over ``filters``, and the gene counts taken."""
    genes_counted: list[str] = []
    detail = de_analysis(filters=filters)

    async def bound_to(_ctx: object) -> ConversationAnalysisView:
        return binding_of(detail)

    async def read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
        del analysis_id
        return detail

    async def preview(_site: str, **_kwargs: object) -> SubsetPreview:
        return counted

    async def genes(
        _site: str, *, study: EdaStudyDetail, entity_id: str, filters: object
    ) -> GeneCount:
        del study, filters
        genes_counted.append(entity_id)
        return DE_GENES

    _wire(monkeypatch, preview)
    monkeypatch.setattr(eda_analysis, "bound_analysis", bound_to)
    monkeypatch.setattr(eda_analysis, "read_analysis", read)
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", de_study)
    monkeypatch.setattr(eda_analysis, "gene_count", genes)
    return genes_counted


def _samples(count: int) -> SubsetPreview:
    return SubsetPreview(
        entity_id=SAMPLE_ENTITY,
        entity_display_name="Sample",
        entity_display_name_plural="Samples",
        count=count,
        unfiltered_count=12,
        distribution=None,
    )


def _count_rows(count: int) -> SubsetPreview:
    return SubsetPreview(
        entity_id=COUNTS_ENTITY,
        entity_display_name="pfal3D7 htseq counts",
        entity_display_name_plural="pfal3D7 htseq counts",
        count=count,
        unfiltered_count=68640,
        distribution=None,
    )


async def test_a_sample_subset_says_it_filters_no_gene(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A count of samples is never reported as a count of genes."""
    counted = _wire_de(monkeypatch, filters=[sample_filter()], counted=_samples(6))

    answer = await eda_analysis.preview_eda_subset(lead_ctx, entity_id=SAMPLE_ENTITY)
    guidance = returned(answer, EdaSubsetPreviewResult).guidance

    assert guidance.endswith(
        "6 of 12 Samples selected; this subset does not filter genes, because "
        "it holds 1 filter on Sample. A step exports genes, so run "
        "run_eda_compute or filter the gene entity pfal3D7 htseq counts "
        "(ENT_fd574cd6) before create_eda_step."
    )
    assert "Genes this subset selects" not in guidance
    assert counted == []


async def test_a_count_of_the_gene_entity_under_a_sample_subset_is_not_genes(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """Rows of a gene-by-sample entity under a sample filter are not a gene count."""
    _wire_de(monkeypatch, filters=[sample_filter()], counted=_count_rows(34320))

    answer = await eda_analysis.preview_eda_subset(lead_ctx, entity_id=COUNTS_ENTITY)

    assert returned(answer, EdaSubsetPreviewResult).guidance.startswith(
        "34,320 of 68,640 pfal3D7 htseq counts selected; this subset does not "
        "filter genes"
    )


async def test_a_count_of_the_gene_entity_under_a_gene_subset_states_its_genes(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """5,114 rows of twelve samples hold 842 genes, and the guidance says 842."""
    counted = _wire_de(monkeypatch, filters=[gene_filter()], counted=_count_rows(5114))

    answer = await eda_analysis.preview_eda_subset(lead_ctx, entity_id=COUNTS_ENTITY)
    result = returned(answer, EdaSubsetPreviewResult)

    assert (result.count, result.unfiltered_count) == (5114, 68640)
    assert "Genes this subset selects: 842 of 5,720, counted as distinct gene ids" in (
        result.guidance
    )
    assert "5,114 of" not in result.guidance
    assert counted == [COUNTS_ENTITY]


async def test_a_sample_count_under_a_gene_subset_also_states_the_gene_count(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    counted = _wire_de(
        monkeypatch, filters=[sample_filter(), gene_filter()], counted=_samples(6)
    )

    answer = await eda_analysis.preview_eda_subset(lead_ctx, entity_id=SAMPLE_ENTITY)
    guidance = returned(answer, EdaSubsetPreviewResult).guidance

    assert "Genes this subset selects: 842 of 5,720" in guidance
    assert "does not filter genes" not in guidance
    assert counted == [COUNTS_ENTITY]
