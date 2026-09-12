"""Return shapes of the EDA tools. Every field is something the model acts on."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field

from pathfinder.services.eda.description import StudyDescription


class EdaStudyCardOut(CamelModel):
    dataset_id: str
    study_id: str
    display_name: str
    short_display_name: str = ""
    description: str = ""
    source_type: str = ""
    relevance: float = 0.0
    can_subset: bool = False
    can_export_rows: bool = False


class EdaStudySearchResult(CamelModel):
    studies: list[EdaStudyCardOut] = Field(default_factory=list)
    guidance: str = ""


class EdaStudyDescription(StudyDescription):
    """One study's shape, plus what the model should do with it."""

    guidance: str = ""


class EdaFiltersResult(CamelModel):
    """Result of one set_eda_filters call."""

    applied: bool = False
    analysis_id: str = ""
    dataset_id: str = ""
    num_filters: int = 0
    # True when this call opened the filter sheet. Nothing is recorded then:
    # the sheet is pinned in the instructions and the next call decides it.
    sheet_pinned: bool = False
    filter_summaries: list[str] = Field(default_factory=list)
    guidance: str = ""


class EdaAnalysisOpened(CamelModel):
    """The analysis this conversation now edits."""

    analysis_id: str
    dataset_id: str
    study_id: str
    display_name: str = ""
    study_display_name: str = ""
    gene_entity_id: str | None = None
    can_export_rows: bool = False
    guidance: str = ""


class EdaSubsetPreviewResult(CamelModel):
    """What the open analysis's filters select on one entity."""

    entity_id: str
    entity_display_name: str = ""
    count: int = 0
    unfiltered_count: int = 0
    variable_id: str | None = None
    variable_display_name: str = ""
    is_multi_valued: bool = False
    labels: list[str] = Field(default_factory=list)
    values: list[float] = Field(default_factory=list)
    num_var_values: int = 0
    num_missing_cases: int = 0
    distribution_note: str | None = None
    guidance: str = ""
