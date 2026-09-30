"""What an exported EDA analysis selects, as a criterion of the spec states it."""

from __future__ import annotations

from enum import StrEnum

from pydantic import ConfigDict, Field
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


class CutTallies(CamelModel):
    """How many genes a compute tested, and how many each reading of its cut keeps.

    ``retained`` keeps the cut's direction; ``retained_up`` and ``retained_down``
    count both sides at the same cut. ``at_any_effect`` relaxes the effect size
    cut to 0 and ``at_any_significance`` the p-value cut to 1, the other cut and
    the direction held.
    """

    model_config = ConfigDict(frozen=True)

    tested: int
    retained: int
    retained_up: int
    retained_down: int
    at_any_effect: int
    at_any_significance: int


class AnalysisBinding(CamelModel):
    """The genes one exported analysis selects, and the document that selects them.

    ``step_parameters`` is the step's own document, carried as an opaque value
    like a saved strategy's subtree. ``value_entity_id`` and ``value_variable``
    name the variable the compute measured; a variable id is scoped to its entity.
    ``effect_size_label`` is the unit of the effect size, as the compute named it.
    """

    dataset_id: str
    comparison: EdaComparison | None = None
    method: str | None = None
    value_entity_id: str | None = None
    value_variable: str | None = None
    effect_direction: EdaEffectDirection | None = None
    effect_size_threshold: float | None = None
    effect_size_label: str = ""
    significance_threshold: float | None = None
    subset: list[str] = Field(default_factory=list)
    words: str
    step_parameters: dict[str, ParamValue] = Field(default_factory=dict)
    # What the export read beside the document: the study's names for the
    # filters and the measured variable, and the counts of the cut.
    shown_subset: list[str] = Field(default_factory=list)
    value_variable_name: str = ""
    tallies: CutTallies | None = None

    def meaning(self) -> AnalysisBinding:
        """The binding as its document states it, without the document itself,
        the words that name it, or what the export read beside it."""
        return self.model_copy(
            update={
                "words": "",
                "step_parameters": {},
                "shown_subset": [],
                "value_variable_name": "",
                "tallies": None,
            }
        )

    def subset_as_shown(self) -> list[str]:
        """The subset in the study's own names, or by variable id when no read
        of the study named them."""
        return self.shown_subset or self.subset
