"""What the thread knows about its open EDA analysis and the step it exported.

Three projections a later turn reads: the analysis the thread holds open, the
analysis as the thread last rendered it, and the cut one export landed in the
strategy.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.model import CamelModel

from pathfinder.domain.eda_parts import EdaEffectDirection, EdaEntityCount


class ConversationAnalysisView(BaseModel):
    """Read shape of a thread's bound analysis."""

    model_config = ConfigDict(frozen=True, from_attributes=True, extra="forbid")

    site_id: str
    dataset_id: str
    analysis_id: str
    revision: int
    subset_previewed: bool = False


class OpenEdaAnalysis(CamelModel):
    """The analysis the thread holds open, as the turn found it.

    ``subset_previewed`` says whether a preview has counted this analysis on
    any message of the thread, so an export can follow the count.
    ``changed_after_the_card`` says the document moved after the card the
    thread shows, through another surface or on the site.
    """

    dataset_id: str
    analysis_id: str
    subset_previewed: bool = False
    changed_after_the_card: bool = False


class EdaAnalysisFacts(CamelModel):
    """The open analysis as the thread last rendered it.

    The wire filters and the revision counter are left out: the summaries say
    what the filters select, and every mutation bumps the revision.
    """

    site_id: str
    dataset_id: str
    study_id: str
    analysis_id: str
    study_display_name: str
    display_name: str
    num_filters: int
    num_computations: int
    filter_summaries: list[str] = Field(default_factory=list)
    entity_counts: list[EdaEntityCount] = Field(default_factory=list)
    can_export_rows: bool


class EdaExport(CamelModel):
    """The EDA cut a turn exported into the strategy, and the step it became."""

    search_name: str
    step_id: str
    dataset_id: str
    analysis_id: str
    is_compute_backed: bool = False
    effect_size_threshold: float | None = None
    significance_threshold: float | None = None
    effect_direction: EdaEffectDirection | None = None
