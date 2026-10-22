from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.outside_changes import outside_changes
from pathfinder.domain.strategy.spec_hydration import (
    StepReading,
    analysis_criteria_stated,
    criteria_listed_under,
    spec_from_ast,
)
from pathfinder.domain.strategy.spec_replay import spec_replaying
from pathfinder.tests.unit.domain.strategy._analysis import (
    COMPUTE_SEARCH,
    EXPORTED,
    binding,
    exported_step,
)

_EXPRESSION = "pfal+pber+pviv>=2T AND tgon=0T"


def _pattern() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_groups",
        search_name="GroupsByPhyleticPattern",
        parameters={"phyletic_expression": StringValue(value=_EXPRESSION)},
    )


def _groups() -> Criterion:
    return Criterion(
        id="step_groups",
        text="groups in most Plasmodium genomes and no Toxoplasma genome",
        search_name="GroupsByPhyleticPattern",
        record_class="group",
        resolved_params={
            "phyletic_expression": BoundValue(
                value=StringValue(value=_EXPRESSION), source="chosen"
            )
        },
    )


def _proteins() -> Criterion:
    return Criterion(
        id="step_proteins",
        text="their proteins",
        search_name="FromGroups",
        record_class="sequence",
        role="transform",
    )


def _proteins_by_taxon() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_groups",
        search_name="ByTaxonomy",
        parameters={"organism": StringValue(value="pfal")},
    )


_LISTED = {
    "GroupsByPhyleticPattern": "group",
    "FromGroups": "sequence",
    "ByTaxonomy": "sequence",
}


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _groups_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="groups in most Plasmodium genomes and no Toxoplasma genome",
        criteria=[_groups()],
        structure=SpecStructure(root=_leaf("step_groups")),
    )


def _proteins_of_the_groups() -> OperationalSpec:
    return OperationalSpec(
        goal="the proteins of those groups",
        criteria=[_groups(), _proteins()],
        structure=SpecStructure(
            root=StructureNode(
                kind="transform",
                criterion_id="step_proteins",
                inputs=[_leaf("step_groups")],
            )
        ),
    )


def test_a_leaf_returns_the_class_its_search_is_listed_under() -> None:
    assert _groups_spec().record_type == "group"


def test_a_transform_returns_its_own_class_and_not_its_inputs() -> None:
    assert _proteins_of_the_groups().record_type == "sequence"


def test_a_combine_returns_the_class_of_an_input_whose_class_is_known() -> None:
    spec = OperationalSpec(
        criteria=[
            Criterion(id="c_waiting", text="a comparison", needs_analysis_on="DS_1"),
            Criterion(
                id="c_pfal",
                text="P. falciparum 3D7 proteins",
                search_name="ByTaxonomy",
                record_class="sequence",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[_leaf("c_waiting"), _leaf("c_pfal")],
            )
        ),
    )

    assert spec.record_type == "sequence"


def test_a_spec_with_no_tree_returns_the_class_of_its_criteria() -> None:
    spec = _groups_spec().model_copy(update={"structure": None})

    assert spec.record_type == "group"


def test_a_spec_whose_classes_are_unknown_has_no_record_type() -> None:
    unclassed = _groups_spec()
    unclassed.criteria[0] = _groups().model_copy(update={"record_class": None})
    empty = OperationalSpec(goal="kinases")

    assert [
        (spec.record_type, [(c.id, c.record_class) for c in spec.criteria])
        for spec in (empty, unclassed)
    ] == [(None, []), (None, [("step_groups", None)])]


def test_a_transform_with_no_class_does_not_take_its_inputs() -> None:
    spec = _proteins_of_the_groups()
    spec.criteria[1] = spec.criteria[1].model_copy(update={"record_class": None})

    assert (spec.record_type, {c.id: c.record_class for c in spec.criteria}) == (
        None,
        {"step_groups": "group", "step_proteins": None},
    )


def test_a_hydrated_spec_takes_the_classes_its_searches_are_listed_under() -> None:
    tree = StrategyAst(record_type="group", root=_pattern())

    hydrated = spec_from_ast(tree, goal="groups", listed=_LISTED)
    unlisted = spec_from_ast(tree, goal="groups", listed={})

    assert (hydrated.record_type, unlisted.record_type) == ("group", None)
    assert [c.record_class for c in hydrated.criteria] == ["group"]


def test_a_listing_keeps_the_class_of_a_criterion_it_does_not_name() -> None:
    listed = criteria_listed_under(_proteins_of_the_groups(), _LISTED)

    assert [c.record_class for c in listed.criteria] == ["group", "sequence"]


def test_an_unbuilt_transform_root_replayed_onto_the_group_strategy_returns_proteins() -> (
    None
):
    tree = StrategyAst(record_type="group", root=_pattern())

    replayed = spec_replaying(
        _proteins_of_the_groups(),
        outside_changes(tree, tree),
        tree,
        StepReading(sheet_params={}, listed=_LISTED, analyses={}),
    )

    assert replayed.record_type == "sequence"


def test_a_search_moved_outside_forgets_the_class_of_the_old_search() -> None:
    answered = StrategyAst(record_type="group", root=_pattern())
    live = StrategyAst(
        record_type="group",
        root=_pattern().model_copy(update={"search_name": "GroupsByGenomeCount"}),
    )

    replayed = spec_replaying(
        _groups_spec(),
        outside_changes(answered, live),
        live,
        StepReading(sheet_params={}, listed={}, analyses={}),
    )

    assert [(c.search_name, c.record_class) for c in replayed.criteria] == [
        ("GroupsByGenomeCount", None)
    ]


def test_a_search_moved_outside_takes_the_class_the_new_search_is_listed_under() -> (
    None
):
    answered = StrategyAst(record_type="group", root=_pattern())
    live = StrategyAst(record_type="sequence", root=_proteins_by_taxon())

    replayed = spec_replaying(
        _groups_spec(),
        outside_changes(answered, live),
        live,
        StepReading(sheet_params={}, listed=_LISTED, analyses={}),
    )

    assert [(c.search_name, c.record_class) for c in replayed.criteria] == [
        ("ByTaxonomy", "sequence")
    ]
    assert replayed.record_type == "sequence"


def test_a_step_gained_outside_takes_the_class_its_search_is_listed_under() -> None:
    answered = StrategyAst(record_type="group", root=_pattern())
    live = StrategyAst(
        record_type="sequence",
        root=StrategyStepNode(
            id="step_proteins",
            search_name="FromGroups",
            primary_input=_pattern(),
        ),
    )

    replayed = spec_replaying(
        _groups_spec(),
        outside_changes(answered, live),
        live,
        StepReading(sheet_params={}, listed=_LISTED, analyses={}),
    )

    assert {c.id: c.record_class for c in replayed.criteria} == {
        "step_groups": "group",
        "step_proteins": "sequence",
    }
    assert replayed.record_type == "sequence"


def test_a_replay_with_no_live_tree_classes_a_criterion_its_listing_names() -> None:
    held = _groups_spec()
    held.criteria[0] = held.criteria[0].model_copy(update={"record_class": None})
    replayed = spec_replaying(
        held,
        outside_changes(None, None),
        None,
        StepReading(sheet_params={}, listed=_LISTED),
    )

    assert [c.record_class for c in replayed.criteria] == ["group"]


def _text_step() -> Criterion:
    return Criterion(
        id=EXPORTED,
        text="kinases",
        search_name="GenesByText",
        record_class="transcript",
    )


def test_a_step_moved_outside_onto_an_analysis_takes_the_analysis_search_class() -> (
    None
):
    held = OperationalSpec(
        goal="kinases higher at 24 h",
        criteria=[_text_step()],
        structure=SpecStructure(root=_leaf(EXPORTED)),
    )
    answered = StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(id=EXPORTED, search_name="GenesByText"),
    )
    live = StrategyAst(record_type="transcript", root=exported_step())

    replayed = [
        spec_replaying(
            held,
            outside_changes(answered, live),
            live,
            StepReading(sheet_params={}, listed=listed, analyses={EXPORTED: binding()}),
        )
        for listed in ({COMPUTE_SEARCH: "transcript"}, {})
    ]

    assert [
        [(c.search_name, c.record_class) for c in spec.criteria] for spec in replayed
    ] == [[(COMPUTE_SEARCH, "transcript")], [(COMPUTE_SEARCH, None)]]


def test_an_analysis_stated_on_the_same_search_keeps_its_class() -> None:
    held = OperationalSpec(
        criteria=[_text_step().model_copy(update={"search_name": COMPUTE_SEARCH})],
        structure=SpecStructure(root=_leaf(EXPORTED)),
    )

    stated = analysis_criteria_stated(held, {EXPORTED: binding()})

    assert [(c.search_name, c.analysis, c.record_class) for c in stated.criteria] == [
        (COMPUTE_SEARCH, binding(), "transcript")
    ]


def test_a_listing_never_replaces_a_class_a_criterion_holds() -> None:
    listed = criteria_listed_under(_groups_spec(), {"GroupsByPhyleticPattern": "x"})

    assert [c.record_class for c in listed.criteria] == ["group"]
