"""What an exported EDA analysis selects, as a criterion of the spec states it."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field
from veupathdb.domain.parameters import ParamValue
from veupathdb.model import CamelModel

from pathfinder.domain.eda_parts import EdaComparison, EdaEffectDirection


class AnalysisKind(StrEnum):
    """Which bridge plugin reads a step's analysis document.

    The query a step's search runs decides it: the compute plugin applies a
    volcano cut, the subset plugin reads the subset alone, and a query that
    declares the document and never reads it exports no analysis.
    """

    COMPUTE = "compute"
    SUBSET = "subset"
    NONE = "none"


class AnalysisBinding(CamelModel):
    """The genes one exported analysis selects, and the document that selects them.

    ``step_parameters`` is the step's own document, carried as an opaque value
    like a saved strategy's subtree.
    """

    dataset_id: str
    comparison: EdaComparison | None = None
    method: str | None = None
    effect_direction: EdaEffectDirection | None = None
    effect_size_threshold: float | None = None
    significance_threshold: float | None = None
    subset: list[str] = Field(default_factory=list)
    words: str
    step_parameters: dict[str, ParamValue] = Field(default_factory=dict)

    def meaning(self) -> AnalysisBinding:
        """The binding without its document, which states no more than it does."""
        return self.model_copy(update={"step_parameters": {}})
