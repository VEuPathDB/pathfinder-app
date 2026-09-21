"""The drafts a stand-in FRAME pass leaves, shared by the disagreement tests."""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
)

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    structure_criteria,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    STAGE,
    STAGE_PERCENTILE,
    Draft,
    built_tree,
    joined,
    leaf,
)

PROTEOME = "c_proteome"
PROTEOME_PARAM = "min_peptide_count"
CANVAS = "step_9f8e7d6c"
CANVAS_ROOT = "step_8e7d6c5b"


def proteome(value: float | None) -> Criterion:
    """A criterion no step answers to yet, open or answered."""
    return Criterion(
        id=PROTEOME,
        text="detected in the merozoite proteome",
        search_name="GenesByMassSpec",
        resolved_params={}
        if value is None
        else {PROTEOME_PARAM: NumberValue(value=value)},
        open_params=[]
        if value is not None
        else [OpenSlot(criterion_id=PROTEOME, param_name=PROTEOME_PARAM)],
    )


def with_the_proteome(value: float | None) -> Draft:
    """The workspace plus the proteome criterion, intersected at the root."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria = [c for c in found.criteria if c.id != PROTEOME]
        found.criteria.append(proteome(value))
        assert found.structure is not None
        if PROTEOME not in structure_criteria(found.structure):
            found.structure = SpecStructure(
                root=joined(CombineOp.INTERSECT, found.structure.root, leaf(PROTEOME))
            )
        return found

    return _draft


def with_the_percentile(value: float) -> Draft:
    """The workspace with one value of the stage criterion moved."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        for criterion in found.criteria:
            if criterion.id == STAGE:
                criterion.resolved_params = {
                    **criterion.resolved_params,
                    STAGE_PERCENTILE: NumberValue(value=value),
                }
        return found

    return _draft


def canvas_step() -> StrategyStepNode:
    return StrategyStepNode(
        id=CANVAS, search_name="GenesByTaxon", display_name="added in the editor"
    )


def tree_with_the_canvas_step() -> StrategyStepNode:
    """The built tree with a step and its combine added in the graph editor."""
    return StrategyStepNode(
        id=CANVAS_ROOT,
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=built_tree(),
        secondary_input=canvas_step(),
    )
