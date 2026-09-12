"""set_eda_filters answers with a sheet, then binds what the model proposed."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from veupathdb.eda import (
    EdaFilter,
    EdaPermissionEntry,
    EdaStringSetFilter,
    EdaStudyDetail,
)

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis
from pathfinder.ai.tools.standalone._eda_models import EdaFiltersResult
from pathfinder.domain.eda_parts import EdaAnalysisState
from pathfinder.services.eda import binding
from pathfinder.services.eda.authoring import SubsetRejectedError
from pathfinder.services.eda.binding import ConversationAnalysisView
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    SPECIES_VARIABLE,
    RevisionCounter,
    permission_entry,
    phenotype_study,
    study_of,
)
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    PHENOTYPE_STUDY,
)
from pathfinder.tests._support.tool_returns import returned


@pytest.fixture(autouse=True)
def revisions(monkeypatch: pytest.MonkeyPatch) -> RevisionCounter:
    counter = RevisionCounter()
    monkeypatch.setattr(binding, "bump_analysis_revision", counter.bump)
    return counter


async def _date_and_number_study(
    _site: str, _dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    variables: list[dict[str, Any]] = [
        {
            "id": "VAR_collected",
            "type": "date",
            "displayName": "Collection date",
            "dataShape": "continuous",
            "distributionDefaults": {
                "rangeMin": "2017-05-05",
                "rangeMax": "2018-01-01",
            },
        },
        {
            "id": "VAR_age",
            "type": "number",
            "displayName": "Age",
            "dataShape": "continuous",
            "distributionDefaults": {"rangeMin": 0.0, "rangeMax": 99.0},
        },
    ]
    return permission_entry(), study_of(variables, entity_id=PHENOTYPE_ENTITY)


async def _longitude_study(
    _site: str, _dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    variables: list[dict[str, Any]] = [
        {
            "id": "VAR_lon",
            "type": "longitude",
            "displayName": "Collection longitude",
            "dataShape": "continuous",
            "distributionDefaults": {"rangeMin": -12.5, "rangeMax": 41.0},
        },
        {
            "id": "VAR_lat",
            "type": "number",
            "displayName": "Collection latitude",
            "dataShape": "continuous",
            "distributionDefaults": {"rangeMin": -8.0, "rangeMax": 15.0},
        },
    ]
    return permission_entry(), study_of(variables, entity_id=PHENOTYPE_ENTITY)


async def _bound(_ctx: object) -> ConversationAnalysisView:
    return ConversationAnalysisView(
        site_id="plasmodb",
        dataset_id=PHENOTYPE_DATASET,
        analysis_id=ANALYSIS_ID,
        revision=1,
    )


async def _unbound(_ctx: object) -> ConversationAnalysisView | None:
    return None


def _species_filter(value: str) -> EdaStringSetFilter:
    return EdaStringSetFilter(
        entity_id=PHENOTYPE_ENTITY, variable_id=SPECIES_VARIABLE, string_set=[value]
    )


def _state(*, num_filters: int) -> EdaAnalysisState:
    return EdaAnalysisState(
        site_id="plasmodb",
        dataset_id=PHENOTYPE_DATASET,
        study_id=PHENOTYPE_STUDY,
        analysis_id=ANALYSIS_ID,
        revision=1,
        study_display_name="Rodent malaria phenotypes",
        display_name="berghei subset",
        num_filters=num_filters,
        num_computations=0,
        filters=[],
        filter_summaries=(["Species is one of P. berghei"] if num_filters else []),
        entity_counts=[],
        can_export_rows=False,
    )


async def _apply_ok(
    _site: str,
    *,
    conversation_id: UUID,
    analysis_id: str,
    dataset_id: str,
    filters: Sequence[EdaFilter],
) -> EdaAnalysisState:
    del conversation_id
    assert analysis_id == ANALYSIS_ID
    assert dataset_id == PHENOTYPE_DATASET
    assert len(filters) == 1
    return _state(num_filters=1)


async def _apply_cleared(
    _site: str,
    *,
    conversation_id: UUID,
    analysis_id: str,
    dataset_id: str,
    filters: Sequence[EdaFilter],
) -> EdaAnalysisState:
    del conversation_id, analysis_id, dataset_id
    assert filters == []
    return _state(num_filters=0)


async def _apply_rejects(
    _site: str,
    *,
    conversation_id: UUID,
    analysis_id: str,
    dataset_id: str,
    filters: Sequence[EdaFilter],
) -> EdaAnalysisState:
    del conversation_id, analysis_id, dataset_id, filters
    raise SubsetRejectedError(
        [
            (
                f"Filter stringSet on variable {SPECIES_VARIABLE} of entity "
                f"{PHENOTYPE_ENTITY} names P. vivax, which the vocabulary does not "
                f"carry. The vocabulary is P. berghei, P. falciparum, P. yoelii."
            )
        ]
    )


async def test_a_first_call_with_no_filters_returns_the_sheet(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", phenotype_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    answer = await eda_analysis.set_eda_filters(lead_ctx, dataset_id=PHENOTYPE_DATASET)
    result = returned(answer, EdaFiltersResult)
    assert result.decide
    assert result.applied is False


async def test_the_sheet_names_the_exact_filter_type_per_variable(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", phenotype_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    answer = await eda_analysis.set_eda_filters(lead_ctx, dataset_id=PHENOTYPE_DATASET)
    result = returned(answer, EdaFiltersResult)
    species = next(e for e in result.decide if e.variable_id == SPECIES_VARIABLE)
    assert species.filter_type == "stringSet"
    assert species.example == {
        "entityId": PHENOTYPE_ENTITY,
        "variableId": SPECIES_VARIABLE,
        "type": "stringSet",
        "stringSet": ["P. berghei"],
    }
    assert species.entity_display_name == "Gene Phenotype Data"


async def test_a_date_example_carries_the_time_part_the_service_requires(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A bare YYYY-MM-DD bound is a server error, so the example never shows one."""
    monkeypatch.setattr(
        eda_analysis, "get_study_detail_for_dataset", _date_and_number_study
    )
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    answer = await eda_analysis.set_eda_filters(lead_ctx, dataset_id=PHENOTYPE_DATASET)
    result = returned(answer, EdaFiltersResult)
    collected = next(e for e in result.decide if e.variable_id == "VAR_collected")
    assert collected.filter_type == "dateRange"
    assert collected.date_min == "2017-05-05T00:00:00"
    assert collected.example["min"] == "2017-05-05T00:00:00"
    age = next(e for e in result.decide if e.variable_id == "VAR_age")
    assert age.filter_type == "numberRange"
    assert age.example == {
        "entityId": PHENOTYPE_ENTITY,
        "variableId": "VAR_age",
        "type": "numberRange",
        "min": 0.0,
        "max": 99.0,
    }


async def test_a_longitude_variable_is_not_a_number_variable(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A longitude takes left and right, so a numberRange on it selects wrongly."""
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", _longitude_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    answer = await eda_analysis.set_eda_filters(lead_ctx, dataset_id=PHENOTYPE_DATASET)
    result = returned(answer, EdaFiltersResult)
    longitude = next(e for e in result.decide if e.variable_id == "VAR_lon")
    assert longitude.filter_type == "longitudeRange"
    assert longitude.example == {
        "entityId": PHENOTYPE_ENTITY,
        "variableId": "VAR_lon",
        "type": "longitudeRange",
        "left": -180.0,
        "right": 180.0,
    }
    latitude = next(e for e in result.decide if e.variable_id == "VAR_lat")
    assert latitude.filter_type == "numberRange"
    assert latitude.example["min"] == -8.0
    assert latitude.example["max"] == 15.0


async def test_a_second_call_applies_the_filters_and_emits_the_state(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", phenotype_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    monkeypatch.setattr(eda_analysis, "apply_filters", _apply_ok)
    answer = await eda_analysis.set_eda_filters(
        lead_ctx,
        dataset_id=PHENOTYPE_DATASET,
        filters=[_species_filter("P. berghei")],
    )
    result = returned(answer, EdaFiltersResult)
    assert result.applied is True
    assert result.num_filters == 1
    assert result.filter_summaries == [
        "Species is one of P. berghei",
    ]
    assert [c.type for c in answer.metadata] == ["data-eda.analysis-state"]
    assert answer.metadata[0].data["revision"] == 1


async def test_an_out_of_vocabulary_value_raises_a_model_retry_with_the_options(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The service would answer 200 with count 0, so the retry is the only signal."""
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", phenotype_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    monkeypatch.setattr(eda_analysis, "apply_filters", _apply_rejects)
    with pytest.raises(ModelRetry) as excinfo:
        await eda_analysis.set_eda_filters(
            lead_ctx,
            dataset_id=PHENOTYPE_DATASET,
            filters=[_species_filter("P. vivax")],
        )
    message = str(excinfo.value)
    assert "P. vivax" in message
    assert "P. berghei" in message
    assert "do not request the sheet again" in message


async def test_calling_with_no_open_analysis_raises_a_model_retry_naming_the_tool(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    monkeypatch.setattr(eda_analysis, "bound_analysis", _unbound)
    with pytest.raises(ModelRetry) as excinfo:
        await eda_analysis.set_eda_filters(
            lead_ctx,
            dataset_id=PHENOTYPE_DATASET,
            filters=[_species_filter("P. berghei")],
        )
    assert "open_eda_analysis" in str(excinfo.value)


async def test_a_dataset_other_than_the_open_one_raises_a_model_retry(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """One conversation edits one analysis, so the argument must name it."""
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    with pytest.raises(ModelRetry) as excinfo:
        await eda_analysis.set_eda_filters(
            lead_ctx,
            dataset_id="DS_eeca6a5476",
            filters=[_species_filter("P. berghei")],
        )
    assert PHENOTYPE_DATASET in str(excinfo.value)


async def test_the_second_sheet_for_the_same_study_omits_the_vocabularies(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The model already holds them; resending costs the whole prompt cache."""
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", phenotype_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    first = returned(
        await eda_analysis.set_eda_filters(lead_ctx, dataset_id=PHENOTYPE_DATASET),
        EdaFiltersResult,
    )
    second = returned(
        await eda_analysis.set_eda_filters(lead_ctx, dataset_id=PHENOTYPE_DATASET),
        EdaFiltersResult,
    )
    assert max(len(e.vocabulary) for e in first.decide) > 0
    assert [len(e.vocabulary) for e in second.decide] == [0] * len(second.decide)
    unnoted = [
        e.variable_id
        for e in second.decide
        if e.vocabulary_total and not e.vocabulary_note
    ]
    assert unnoted == []


async def test_an_empty_filter_list_clears_the_subset(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """An analysis with no filters is legal and means the whole study."""
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", phenotype_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)
    monkeypatch.setattr(eda_analysis, "apply_filters", _apply_cleared)
    answer = await eda_analysis.set_eda_filters(
        lead_ctx, dataset_id=PHENOTYPE_DATASET, filters=[]
    )
    result = returned(answer, EdaFiltersResult)
    assert result.applied is True
    assert result.num_filters == 0
