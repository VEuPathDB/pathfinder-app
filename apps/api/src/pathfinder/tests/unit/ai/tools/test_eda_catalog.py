"""The catalog tools: what search returns and what describe tells the model."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_catalog
from pathfinder.integrations.eda.models import EdaPermissionEntry, EdaStudyDetail
from pathfinder.services.eda.catalog import (
    NAME_MATCH_GUIDANCE,
    StudyCard,
    StudySearch,
    UnknownEdaDatasetError,
)
from pathfinder.tests._support.eda_doubles import (
    no_gene_study,
    permission_entry,
    phenotype_study,
    study_of,
)
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    PHENOTYPE_STUDY,
)

StudyResolver = Any


async def _wide_vocabulary_study(
    _site: str, _dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    wide = {
        "id": "VAR_wide",
        "type": "string",
        "displayName": "Sample id",
        "dataShape": "categorical",
        "isMultiValued": False,
        "vocabulary": [f"term-{index}" for index in range(500)],
    }
    return permission_entry(), study_of([wide], entity_id="E")


async def _multifilter_study(
    _site: str, _dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    category = {
        "id": "VAR_category",
        "type": "category",
        "displayName": "Assay results",
        "displayType": "multifilter",
    }
    children = [
        {
            "id": f"VAR_child_{index}",
            "type": "string",
            "displayName": f"Child {index}",
            "parentId": "VAR_category",
            "dataShape": "categorical",
            "vocabulary": ["yes", "no"],
        }
        for index in range(2)
    ]
    return permission_entry(), study_of(
        [category, *children], entity_id="EUPATH_0000096"
    )


async def _hidden_everywhere_study(
    _site: str, _dataset_id: str
) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
    hidden = {
        "id": "VAR_hidden",
        "type": "string",
        "displayName": "Internal batch",
        "dataShape": "categorical",
        "vocabulary": ["batch-1", "batch-2"],
        "hideFrom": ["everywhere"],
    }
    return permission_entry(), study_of([hidden], entity_id=PHENOTYPE_ENTITY)


def _serve_study(monkeypatch: pytest.MonkeyPatch, resolver: StudyResolver) -> None:
    monkeypatch.setattr(eda_catalog, "get_study_detail_for_dataset", resolver)


async def test_search_eda_studies_returns_cards_the_model_can_act_on(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    async def found(_site: str, _query: str, limit: int = 5) -> StudySearch:
        del limit
        return StudySearch(
            cards=[
                StudyCard(
                    dataset_id=PHENOTYPE_DATASET,
                    study_id=PHENOTYPE_STUDY,
                    display_name="Rodent malaria phenotypes",
                    short_display_name="Rod Mal Phenotype",
                    description="Phenotypes of genetically modified rodent malaria",
                    source_type="curated",
                    relevance=0.71,
                    can_subset=True,
                    can_export_rows=True,
                )
            ]
        )

    monkeypatch.setattr(eda_catalog, "search_studies", found)
    result = (
        await eda_catalog.search_eda_studies(lead_ctx, query="rodent malaria")
    ).return_value
    assert result.studies
    first = result.studies[0]
    assert first.dataset_id == PHENOTYPE_DATASET
    assert first.study_id == PHENOTYPE_STUDY
    assert first.can_export_rows is True
    assert "Phenotypes" in first.description
    assert "describe_eda_study" in result.guidance


async def test_search_eda_studies_says_so_when_nothing_matches(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    async def none(_site: str, _query: str, limit: int = 5) -> StudySearch:
        del limit
        return StudySearch(cards=[])

    monkeypatch.setattr(eda_catalog, "search_studies", none)
    result = (
        await eda_catalog.search_eda_studies(lead_ctx, query="nothing here")
    ).return_value
    assert result.studies == []
    assert "No EDA study" in result.guidance


async def test_search_eda_studies_carries_the_name_match_guidance(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """An unbuilt index degrades to a name match, and the model is told."""
    card = StudyCard(
        dataset_id="DS_heat",
        study_id="STUDY_heat",
        display_name="Heat shock response",
        short_display_name="",
        description="",
        source_type="curated",
    )

    async def by_name(_site: str, _query: str, limit: int = 5) -> StudySearch:
        del limit
        return StudySearch(cards=[card], guidance=NAME_MATCH_GUIDANCE)

    monkeypatch.setattr(eda_catalog, "search_studies", by_name)
    result = (
        await eda_catalog.search_eda_studies(lead_ctx, query="gametocyte")
    ).return_value

    assert [study.dataset_id for study in result.studies] == ["DS_heat"]
    assert result.guidance.startswith(NAME_MATCH_GUIDANCE)


async def test_describe_eda_study_reports_the_entity_tree_and_the_gene_entity(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _serve_study(monkeypatch, phenotype_study)
    result = (
        await eda_catalog.describe_eda_study(lead_ctx, dataset_id=PHENOTYPE_DATASET)
    ).return_value
    assert result.study_id == PHENOTYPE_STUDY
    assert result.gene_entity_id == PHENOTYPE_ENTITY
    entities = {e.entity_id: e for e in result.entities}
    assert PHENOTYPE_ENTITY in entities
    assert entities[PHENOTYPE_ENTITY].variable_count > 0
    assert entities[PHENOTYPE_ENTITY].has_gene_id is True
    assert result.variables == []


async def test_describe_eda_study_summarises_a_vocabulary_without_dumping_it(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A tool payload must fit a context window; 4000 terms must not travel."""
    _serve_study(monkeypatch, phenotype_study)
    result = (
        await eda_catalog.describe_eda_study(
            lead_ctx, dataset_id=PHENOTYPE_DATASET, entity_id=PHENOTYPE_ENTITY
        )
    ).return_value
    species = next(v for v in result.variables if v.variable_id == "VAR_035294d0")
    assert species.vocabulary_total == 3
    assert species.vocabulary == ["P. berghei", "P. falciparum", "P. yoelii"]
    assert species.is_multi_valued is True
    assert species.filter_type == "stringSet"
    assert species.entity_id == PHENOTYPE_ENTITY


async def test_describe_eda_study_lists_a_variable_the_site_hides_everywhere(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """hideFrom is UI advice, not access control; the variable is still filterable."""
    _serve_study(monkeypatch, _hidden_everywhere_study)
    result = (
        await eda_catalog.describe_eda_study(
            lead_ctx, dataset_id=PHENOTYPE_DATASET, entity_id=PHENOTYPE_ENTITY
        )
    ).return_value
    hidden = next(v for v in result.variables if v.variable_id == "VAR_hidden")
    assert hidden.filter_type == "stringSet"
    assert hidden.vocabulary == ["batch-1", "batch-2"]


async def test_describe_eda_study_truncates_a_long_vocabulary_and_says_so(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _serve_study(monkeypatch, _wide_vocabulary_study)
    result = (
        await eda_catalog.describe_eda_study(
            lead_ctx, dataset_id=PHENOTYPE_DATASET, entity_id="E"
        )
    ).return_value
    wide = result.variables[0]
    assert wide.vocabulary_total == 500
    assert len(wide.vocabulary) == 40
    assert wide.vocabulary_note is not None
    assert "500" in wide.vocabulary_note


async def test_describe_eda_study_names_a_multifilter_category_and_its_children(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _serve_study(monkeypatch, _multifilter_study)
    result = (
        await eda_catalog.describe_eda_study(
            lead_ctx, dataset_id=PHENOTYPE_DATASET, entity_id="EUPATH_0000096"
        )
    ).return_value
    category = next(v for v in result.variables if v.filter_type == "multiFilter")
    assert category.sub_filter_variable_ids == ["VAR_child_0", "VAR_child_1"]
    assert category.vocabulary == []


async def test_describe_eda_study_refuses_a_study_with_no_gene_id_variable(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    _serve_study(monkeypatch, no_gene_study)
    result = (
        await eda_catalog.describe_eda_study(lead_ctx, dataset_id=PHENOTYPE_DATASET)
    ).return_value
    assert result.gene_entity_id is None
    assert result.gene_entity_problem is not None
    assert "VEUPATHDB_GENE_ID" in result.gene_entity_problem


async def test_an_unknown_dataset_id_raises_a_model_retry_naming_the_tool(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    async def raises(
        _site: str, _dataset_id: str
    ) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
        unknown = "DS_nope"
        raise UnknownEdaDatasetError(unknown, ["DS_a", "DS_b"])

    _serve_study(monkeypatch, raises)
    with pytest.raises(ModelRetry) as excinfo:
        await eda_catalog.describe_eda_study(lead_ctx, dataset_id="DS_nope")
    assert "DS_nope" in str(excinfo.value)
    assert "search_eda_studies" in str(excinfo.value)
