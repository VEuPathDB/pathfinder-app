"""The drafts a stand-in FRAME pass leaves, and the edits a canvas commits."""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue, ParamValue, StringValue
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
from pathfinder.domain.strategy.operations import (
    DeleteStepOp,
    UpdateCombineOperatorOp,
    UpdateStepParamsOp,
)
from pathfinder.domain.strategy.operations.apply import apply_operation
from pathfinder.domain.strategy.operations.resolutions import compute_delete_choices
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    STAGE,
    STAGE_PERCENTILE,
    Draft,
    built_spec,
    built_tree,
    joined,
    leaf,
)

PROTEOME = "c_proteome"
PROTEOME_PARAM = "min_peptide_count"
CANVAS = "step_9f8e7d6c"
CANVAS_ROOT = "step_8e7d6c5b"


THIRD = "step_3d4e5f6a"
NESTED_ROOT = "step_4e5f6a7b"
THIRD_PARAM = "organism"
THIRD_SEARCH = "GenesByTaxon"


def third_step() -> StrategyStepNode:
    return StrategyStepNode(
        id=THIRD,
        search_name=THIRD_SEARCH,
        display_name="Plasmodium falciparum",
        parameters={THIRD_PARAM: StringValue(value="Pf3D7")},
    )


def nested_tree() -> StrategyStepNode:
    """``((surface INTERSECT stage) INTERSECT taxon)``, three searches deep."""
    return StrategyStepNode(
        id=NESTED_ROOT,
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=built_tree(),
        secondary_input=third_step(),
    )


def nested_spec() -> OperationalSpec:
    """The spec the three-step build left, each criterion on its own step."""
    spec = built_spec()
    spec.criteria.append(
        Criterion(
            id=THIRD,
            text="Plasmodium falciparum",
            search_name=THIRD_SEARCH,
            resolved_params={THIRD_PARAM: StringValue(value="Pf3D7")},
        )
    )
    assert spec.structure is not None
    spec.structure = SpecStructure(
        root=joined(CombineOp.INTERSECT, spec.structure.root, leaf(THIRD))
    )
    return spec


def canvas_sets(graph: StrategyGraph, step_id: str, **values: ParamValue) -> None:
    """Set values on one step the way the graph route commits them."""
    apply_operation(graph, UpdateStepParamsOp(step_id=step_id, parameters=values))


def canvas_flips(graph: StrategyGraph, step_id: str, operator: CombineOp) -> None:
    apply_operation(graph, UpdateCombineOperatorOp(step_id=step_id, operator=operator))


def canvas_deletes(graph: StrategyGraph, step_id: str) -> list[str]:
    """Delete one step the way the graph route does, and name what left."""
    choices = compute_delete_choices(graph, step_id)
    chosen = next((c for c in choices if c.is_default), choices[0])
    result = apply_operation(
        graph, DeleteStepOp(step_id=step_id, resolution=chosen.resolution)
    )
    return sorted(result.dropped_step_ids)


def canvas_renames(graph: StrategyGraph, step_id: str, display_name: str) -> None:
    graph.steps[step_id].display_name = display_name


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
