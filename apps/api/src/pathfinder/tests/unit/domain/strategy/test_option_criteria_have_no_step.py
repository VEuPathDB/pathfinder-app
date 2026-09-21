"""A criterion the structure does not name binds an option, not a step.

The build mints a step for the criteria the structure names. A criterion that
names an option on another criterion's search answers to that criterion's step,
so no measurement and no refusal may ask it for a step of its own, and the
values it states ride that step.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import CombineOp, flatten_tree

from pathfinder.domain.strategy.edit_plan import UnsupportedEditError
from pathfinder.domain.strategy.operational_spec import (
    AssumedValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    build_step_tree,
    fold_option_criteria,
    renumber_criteria,
    structure_criteria,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_diff import diff_specs
from pathfinder.domain.strategy.spec_to_operations import operations_for
from pathfinder.domain.strategy.stated_shape import (
    criteria_with_steps,
    stated_shape,
)

_EXPRESSION = "gametocyte_expression"
_OPTION = "gametocyte_timecourse_option"
_SEARCH = "GenesByRNASeqEvidence"
_DEFAULT_DATASET = "all_rnaseq"
_TIMECOURSE = "pfal3D7_Gametocyte_Timecourse_rnaSeq"
_SEXUAL_STAGE = "pfal3D7_Sexual_Stage_rnaSeq"
_SEXUAL_STAGE_OPTION = "sexual_stage_option"


def _framed() -> OperationalSpec:
    """Two criteria, one of which the structure does not name.

    Both calls resolved every parameter of the search, so the option criterion
    states a dataset beside an organism it only defaulted.
    """
    return OperationalSpec(
        goal="genes upregulated in gametocytes",
        record_type="transcript",
        criteria=[
            Criterion(
                id=_EXPRESSION,
                text="upregulated in gametocytes",
                search_name=_SEARCH,
                resolved_params={
                    "organism": MultiPickValue(values=["Pf3D7"]),
                    "dataset": StringValue(value=_DEFAULT_DATASET),
                },
                defaulted_params=["dataset"],
            ),
            Criterion(
                id=_OPTION,
                text="use the gametocyte timecourse dataset",
                search_name=_SEARCH,
                resolved_params={
                    "organism": MultiPickValue(values=["Pfalciparum"]),
                    "dataset": StringValue(value=_TIMECOURSE),
                },
                defaulted_params=["organism"],
                assumptions=[
                    AssumedValue(
                        param_name="dataset",
                        value=_TIMECOURSE,
                        reason="the request names the gametocyte timecourse",
                    ),
                ],
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=_EXPRESSION)
        ),
    )


def _framed_with_two_carriers() -> OperationalSpec:
    """A framed spec where two steps run the search the option names."""
    spec = _framed()
    spec.criteria.append(
        Criterion(id="second_expression", text="a second read", search_name=_SEARCH)
    )
    spec.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            inputs=[_leaf(_EXPRESSION), _leaf("second_expression")],
        )
    )
    return spec


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _built() -> tuple[OperationalSpec, StrategyGraph]:
    spec = _framed()
    tree = build_step_tree(spec)
    graph = StrategyGraph(graph_id="g1", name="gametocytes", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(tree.root)
    graph.recompute_roots()
    graph.last_step_id = tree.root.id
    return renumber_criteria(spec, tree.step_id_by_criterion), graph


def _plan(
    before: OperationalSpec, after: OperationalSpec, graph: StrategyGraph
) -> list[str]:
    ops = operations_for(diff_specs(before, after), after=after, graph=graph)
    return [op.kind for op in ops]


def test_the_built_step_carries_the_option_the_spec_states() -> None:
    """The stated dataset reaches the step, and a defaulted value does not."""
    tree = build_step_tree(fold_option_criteria(_framed()).spec)

    assert tree.root.parameters == {
        "organism": MultiPickValue(values=["Pf3D7"]),
        "dataset": StringValue(value=_TIMECOURSE),
    }
    assert list(tree.step_id_by_criterion) == [_EXPRESSION]


def test_the_folded_criterion_states_what_both_criteria_asked() -> None:
    folded = fold_option_criteria(_framed())

    (criterion,) = folded.spec.criteria
    assert criterion.id == _EXPRESSION
    assert criterion.resolved_params["dataset"] == StringValue(value=_TIMECOURSE)
    assert criterion.defaulted_params == []
    assert [a.param_name for a in criterion.assumptions] == ["dataset"]


def test_a_structure_that_names_every_criterion_folds_nothing() -> None:
    spec = _framed()
    spec.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[_leaf(_EXPRESSION), _leaf(_OPTION)],
        )
    )

    folded = fold_option_criteria(spec)

    assert folded.spec is spec
    assert [c.id for c in folded.spec.criteria] == [_EXPRESSION, _OPTION]


def test_a_criterion_of_another_search_is_left_where_it_is() -> None:
    """Only the search the step runs can carry the values a criterion states."""
    spec = _framed()
    spec.criteria[1].search_name = "GenesByTaxon"

    folded = fold_option_criteria(spec)

    assert [c.id for c in folded.spec.criteria] == [_EXPRESSION, _OPTION]
    assert folded.spec.criteria[0].resolved_params["dataset"] == StringValue(
        value=_DEFAULT_DATASET
    )


def test_an_option_two_steps_could_carry_is_left_where_it_is() -> None:
    """Two steps run the search, so which one states the option is unknown."""
    spec = _framed_with_two_carriers()

    folded = fold_option_criteria(spec)

    assert [c.id for c in folded.spec.criteria] == [
        _EXPRESSION,
        _OPTION,
        "second_expression",
    ]


def test_the_build_mints_no_step_for_a_criterion_the_structure_leaves_out() -> None:
    before, graph = _built()

    assert _OPTION not in graph.steps
    assert [c.id for c in before.criteria] == [graph.last_step_id, _OPTION]


def test_the_stated_criteria_are_the_ones_that_answer_to_a_step() -> None:
    before, graph = _built()

    stated = criteria_with_steps(
        [c.id for c in before.criteria],
        graph.steps,
        minted=structure_criteria(before.structure),
    )

    assert stated == frozenset({graph.last_step_id})


def test_an_added_criterion_answers_to_the_step_the_structure_states() -> None:
    """The edit mints its step, so the shape counts it before it exists."""
    before, graph = _built()
    root_id = graph.last_step_id
    assert root_id is not None

    stated = criteria_with_steps(
        [*(c.id for c in before.criteria), "new_leaf"],
        graph.steps,
        minted=structure_criteria(
            SpecStructure(
                root=StructureNode(
                    kind="combine",
                    operator=None,
                    inputs=[_leaf(root_id), _leaf("new_leaf")],
                )
            )
        ),
    )

    assert stated == frozenset({root_id, "new_leaf"})


def test_an_option_criterion_is_never_reported_lost() -> None:
    before, graph = _built()

    shape = stated_shape(
        graph=graph,
        root_id=graph.primary_root_id() or "",
        criteria=criteria_with_steps(
            [c.id for c in before.criteria],
            graph.steps,
            minted=structure_criteria(before.structure),
        ),
        outside=set(),
    )

    assert shape.lost == ()
    assert shape.unstated == ()
    assert shape.holds is True


def test_an_edit_that_keeps_both_criteria_plans_nothing() -> None:
    before, graph = _built()

    assert _plan(before, before.model_copy(deep=True), graph) == []


def test_an_edit_that_restates_the_option_value_is_not_refused() -> None:
    """An option criterion owes no step, so restating its value is a valid edit."""
    before, graph = _built()
    after = before.model_copy(deep=True)
    for criterion in after.criteria:
        if criterion.id == _OPTION:
            criterion.resolved_params = {
                "dataset": StringValue(value="gametocyte_timecourse")
            }

    assert _plan(before, after, graph) == []


def test_an_edit_that_drops_the_option_criterion_plans_nothing() -> None:
    before, graph = _built()
    after = before.model_copy(deep=True)
    after.criteria = [c for c in after.criteria if c.id != _OPTION]

    assert _plan(before, after, graph) == []


def test_a_refusal_names_no_criterion_that_can_have_no_step() -> None:
    """A structure that states none of the live steps is still refused."""
    before, graph = _built()
    after = before.model_copy(deep=True)
    after.criteria = [
        *after.criteria,
        Criterion(id="added_leaf", text="a second search", search_name="GenesByTaxon"),
    ]
    after.structure = SpecStructure(root=_leaf("added_leaf"))

    with pytest.raises(UnsupportedEditError) as excinfo:
        _plan(before, after, graph)

    assert _OPTION not in str(excinfo.value)


def test_the_carrier_keeps_a_value_it_states_of_its_own() -> None:
    """The option fills what the carrier leaves open, never what it states."""
    spec = _framed()
    spec.criteria[1].resolved_params["organism"] = MultiPickValue(values=["Pvivax"])
    spec.criteria[1].defaulted_params = []

    (carrier,) = fold_option_criteria(spec).spec.criteria

    assert carrier.resolved_params == {
        "organism": MultiPickValue(values=["Pf3D7"]),
        "dataset": StringValue(value=_TIMECOURSE),
    }


def test_the_carrier_keeps_its_text_and_assumes_the_option() -> None:
    """The step name stays the carrier's, and the option rides as a constraint."""
    (carrier,) = fold_option_criteria(_framed()).spec.criteria

    assert carrier.text == "upregulated in gametocytes"
    assert carrier.assumptions == [
        AssumedValue(
            param_name="dataset",
            value=_TIMECOURSE,
            reason="use the gametocyte timecourse dataset",
            carried_from=_OPTION,
        )
    ]


def test_an_option_two_steps_could_carry_is_reported_unplaced() -> None:
    spec = _framed_with_two_carriers()

    assert fold_option_criteria(spec).unplaced == (_OPTION,)


def test_an_option_no_step_runs_the_search_for_is_reported_unplaced() -> None:
    spec = _framed()
    spec.criteria[1].search_name = "GenesByTaxon"

    assert fold_option_criteria(spec).unplaced == (_OPTION,)


def _second_option(dataset: str) -> Criterion:
    return Criterion(
        id=_SEXUAL_STAGE_OPTION,
        text="use the sexual stage dataset",
        search_name=_SEARCH,
        resolved_params={"dataset": StringValue(value=dataset)},
    )


def test_two_options_that_state_one_value_fold_once() -> None:
    """The second statement of a value the fold carried has nothing to do."""
    spec = _framed()
    spec.criteria.append(_second_option(_TIMECOURSE))

    folded = fold_option_criteria(spec)

    (carrier,) = folded.spec.criteria
    assert folded.unplaced == ()
    assert carrier.resolved_params["dataset"] == StringValue(value=_TIMECOURSE)
    assert [a.reason for a in carrier.assumptions] == [
        "use the gametocyte timecourse dataset"
    ]


def test_an_option_that_contradicts_a_carried_value_is_reported_unplaced() -> None:
    """Two options state one parameter two ways, so neither value is the answer."""
    spec = _framed()
    spec.criteria.append(_second_option(_SEXUAL_STAGE))

    folded = fold_option_criteria(spec)

    assert folded.unplaced == (_SEXUAL_STAGE_OPTION,)
    assert [c.id for c in folded.spec.criteria] == [_EXPRESSION, _SEXUAL_STAGE_OPTION]
    assert folded.spec.criteria[0].resolved_params["dataset"] == StringValue(
        value=_TIMECOURSE
    )


def _frame_assumed_carrier() -> OperationalSpec:
    """The carrier's dataset is a value the model chose, not one its text states."""
    spec = _framed()
    spec.criteria[0].defaulted_params = []
    spec.criteria[0].assumptions = [
        AssumedValue(
            param_name="dataset",
            value=_DEFAULT_DATASET,
            reason="the request names no dataset",
        )
    ]
    return spec


def test_an_option_overrides_a_value_the_carrier_assumed() -> None:
    """The user's choice replaces the model's guess and records which one it is."""
    folded = fold_option_criteria(_frame_assumed_carrier())

    (carrier,) = folded.spec.criteria
    assert folded.unplaced == ()
    assert carrier.resolved_params["dataset"] == StringValue(value=_TIMECOURSE)
    assert carrier.assumptions == [
        AssumedValue(
            param_name="dataset",
            value=_TIMECOURSE,
            reason="use the gametocyte timecourse dataset",
            carried_from=_OPTION,
        )
    ]


def test_an_assumption_the_option_does_not_name_stays() -> None:
    spec = _frame_assumed_carrier()
    spec.criteria[0].assumptions.insert(
        0,
        AssumedValue(
            param_name="organism",
            value='["Pf3D7"]',
            reason="the request names one strain",
        ),
    )

    (carrier,) = fold_option_criteria(spec).spec.criteria

    assert [(a.param_name, a.reason) for a in carrier.assumptions] == [
        ("organism", "the request names one strain"),
        ("dataset", "use the gametocyte timecourse dataset"),
    ]
