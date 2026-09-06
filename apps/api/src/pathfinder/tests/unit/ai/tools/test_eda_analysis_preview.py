"""preview_eda_subset reports both counts and narrates what the numbers mean."""

from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.eda.models import EdaDistributionResponse

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis
from pathfinder.services.eda import binding
from pathfinder.services.eda.authoring import SubsetPreview
from pathfinder.services.eda.binding import ConversationAnalysisView
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    SPECIES_VARIABLE,
    RevisionCounter,
    phenotype_study,
    read_analysis_detail,
    recorded_entity_counts,
)
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    fixture,
)


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


def _wire(monkeypatch: pytest.MonkeyPatch, preview: object) -> None:
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    monkeypatch.setattr(eda_analysis, "read_analysis", read_analysis_detail)
    monkeypatch.setattr(eda_analysis, "preview_subset", preview)
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", phenotype_study)


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
    returned = await eda_analysis.preview_eda_subset(
        lead_ctx,
        entity_id=PHENOTYPE_ENTITY,
        distribution_variable_id=SPECIES_VARIABLE,
    )
    assert returned.return_value.count == 4011
    assert returned.return_value.unfiltered_count == 4279
    assert returned.return_value.labels == [
        "P. berghei",
        "P. falciparum",
        "P. yoelii",
    ]
    assert returned.return_value.values == [4011.0, 4130.0, 268.0]
    assert [c.type for c in returned.metadata] == ["data-eda.subset-preview"]


async def test_a_preview_puts_the_model_s_caption_on_the_part(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The figure reads the model's sentence, so the tool must carry it."""
    _wire(monkeypatch, _preview_ok)
    returned = await eda_analysis.preview_eda_subset(
        lead_ctx,
        entity_id=PHENOTYPE_ENTITY,
        distribution_variable_id=SPECIES_VARIABLE,
        caption="Species of the phenotyped genes the filters keep",
    )
    assert _captions(returned.metadata) == [
        "Species of the phenotyped genes the filters keep"
    ]


async def test_a_preview_with_no_caption_leaves_the_part_s_caption_empty(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, _preview_ok)
    returned = await eda_analysis.preview_eda_subset(
        lead_ctx, entity_id=PHENOTYPE_ENTITY
    )
    assert _captions(returned.metadata) == [""]


async def test_a_preview_of_zero_says_which_filter_emptied_the_subset(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """Zero is a real answer and the model must not silently narrate a result."""
    _wire(monkeypatch, _preview_zero)
    returned = await eda_analysis.preview_eda_subset(
        lead_ctx, entity_id=PHENOTYPE_ENTITY
    )
    assert returned.return_value.count == 0
    assert "selects no records" in returned.return_value.guidance


async def test_a_preview_of_zero_reports_its_summary_as_empty(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The line carries the zero and the status says empty, never ok."""
    _wire(monkeypatch, _preview_zero)
    ctx = replace(lead_ctx, tool_call_id="call_1")
    returned = await eda_analysis.preview_eda_subset(ctx, entity_id=PHENOTYPE_ENTITY)
    summaries = [
        chunk.data
        for chunk in returned.metadata
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
    returned = await eda_analysis.preview_eda_subset(
        lead_ctx, entity_id=PHENOTYPE_ENTITY
    )
    assert "narrow nothing here" in returned.return_value.guidance


async def test_a_multi_valued_distribution_warns_that_the_values_do_not_partition(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, _preview_ok)
    returned = await eda_analysis.preview_eda_subset(
        lead_ctx,
        entity_id=PHENOTYPE_ENTITY,
        distribution_variable_id=SPECIES_VARIABLE,
    )
    assert returned.return_value.is_multi_valued is True
    assert "several values per record" in returned.return_value.guidance


async def test_a_preview_reports_the_records_with_no_value_for_the_variable(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _wire(monkeypatch, _preview_with_missing)
    returned = await eda_analysis.preview_eda_subset(
        lead_ctx,
        entity_id=PHENOTYPE_ENTITY,
        distribution_variable_id=SPECIES_VARIABLE,
    )
    assert returned.return_value.num_missing_cases == 12
    assert "12 records" in returned.return_value.guidance


async def test_a_preview_with_no_open_analysis_raises_a_model_retry(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    monkeypatch.setattr(eda_analysis, "bound_analysis", _unbound)
    with pytest.raises(ModelRetry) as excinfo:
        await eda_analysis.preview_eda_subset(lead_ctx, entity_id=PHENOTYPE_ENTITY)
    assert "open_eda_analysis" in str(excinfo.value)
