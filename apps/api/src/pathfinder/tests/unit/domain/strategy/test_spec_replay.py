"""What an outside change does to the spec the strategy answered to.

A value the researcher set outside is their statement: the criterion takes it
and everything it said about that name retires with it.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from veupathdb.domain.parameters import NumberValue, ParamValue, StringValue
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.operational_spec import (
    AssumedValue,
    Criterion,
    OpenSlot,
    OperationalSpec,
    ParameterAlternatives,
    SpecStructure,
    StructureNode,
    structure_criteria,
)
from pathfinder.domain.strategy.outside_changes import outside_changes
from pathfinder.domain.strategy.spec_replay import spec_replaying

from ._builders import combine, leaf

_PERCENTILE = "min_expression_percentile"
_HIDDEN = "wdk_weight_bucket"
_SHEETS: Mapping[str, Collection[str]] = {
    "GenesByRNASeqEvidence": frozenset({_PERCENTILE, "timepoint"}),
    "GenesByText": frozenset({"text_expression"}),
    "GenesByGoTerm": frozenset({"go_term"}),
}


def _expression(
    percentile: int = 80,
    *,
    step_id: str = "expr",
    search_name: str = "GenesByRNASeqEvidence",
    hidden: int | None = None,
) -> StrategyStepNode:
    parameters: dict[str, ParamValue] = {_PERCENTILE: NumberValue(value=percentile)}
    if hidden is not None:
        parameters[_HIDDEN] = NumberValue(value=hidden)
    return StrategyStepNode(id=step_id, search_name=search_name, parameters=parameters)


def _ast(root: StrategyStepNode) -> StrategyAst:
    return StrategyAst(record_type="transcript", root=root)


def _built(percentile: int = 80, hidden: int | None = None) -> StrategyAst:
    return _ast(
        combine(
            "c0",
            StrategyStepNode(id="text", search_name="GenesByText"),
            _expression(percentile, hidden=hidden),
        )
    )


def _spec() -> OperationalSpec:
    """The spec that answered to ``_built()``: one criterion per step."""
    return OperationalSpec(
        goal="ring stage kinases",
        criteria=[
            Criterion(id="text", text="kinase", search_name="GenesByText"),
            Criterion(
                id="expr",
                text="expressed in rings",
                search_name="GenesByRNASeqEvidence",
                resolved_params={_PERCENTILE: NumberValue(value=80)},
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="text"),
                    StructureNode(kind="leaf", criterion_id="expr"),
                ],
            )
        ),
    )


def _replayed(
    spec: OperationalSpec, answered: StrategyAst, live: StrategyAst | None
) -> OperationalSpec:
    return spec_replaying(
        spec, outside_changes(answered, live), live, sheet_params=_SHEETS, analyses={}
    )


def _criterion(spec: OperationalSpec, criterion_id: str) -> Criterion:
    return next(c for c in spec.criteria if c.id == criterion_id)


def test_a_value_set_outside_reaches_the_criterion() -> None:
    replayed = _replayed(_spec(), _built(80), _built(48))

    assert _criterion(replayed, "expr").resolved_params[_PERCENTILE] == NumberValue(
        value=48
    )


def test_a_value_the_sheet_does_not_show_is_left_to_the_strategy() -> None:
    """A hidden parameter is WDK's, and a criterion states none of them."""
    replayed = _replayed(_spec(), _built(80), _built(80, hidden=3))

    assert _criterion(replayed, "expr").resolved_params == {
        _PERCENTILE: NumberValue(value=80)
    }


def test_a_value_taken_off_the_step_leaves_the_criterion() -> None:
    stripped = _ast(
        combine(
            "c0",
            StrategyStepNode(id="text", search_name="GenesByText"),
            StrategyStepNode(id="expr", search_name="GenesByRNASeqEvidence"),
        )
    )

    replayed = _replayed(_spec(), _built(80), stripped)

    assert _criterion(replayed, "expr").resolved_params == {}


def test_a_replayed_value_closes_the_open_slot_that_asked_for_it() -> None:
    spec = _spec()
    _criterion(spec, "expr").open_params = [
        OpenSlot(criterion_id="expr", param_name=_PERCENTILE)
    ]
    spec.open_slots = [OpenSlot(criterion_id="expr", param_name=_PERCENTILE)]

    replayed = _replayed(spec, _built(80), _built(48))

    assert _criterion(replayed, "expr").open_params == []
    assert replayed.open_slots == []
    assert replayed.ready_to_build


def test_a_replayed_value_is_no_longer_a_default() -> None:
    spec = _spec()
    _criterion(spec, "expr").defaulted_params = [_PERCENTILE, "timepoint"]

    replayed = _replayed(spec, _built(80), _built(48))

    assert _criterion(replayed, "expr").defaulted_params == ["timepoint"]


def test_a_replayed_value_retires_the_assumption_a_fold_carried() -> None:
    """The carried wire value is the old one, so it may not outlive it."""
    spec = _spec()
    _criterion(spec, "expr").assumptions = [
        AssumedValue(
            param_name=_PERCENTILE,
            value="80",
            reason="ring stage",
            carried_from="c_stage",
        ),
        AssumedValue(param_name="timepoint", value="40", reason="mid ring"),
    ]

    replayed = _replayed(spec, _built(80), _built(48))

    assert [a.param_name for a in _criterion(replayed, "expr").assumptions] == [
        "timepoint"
    ]


def test_a_replayed_value_retires_the_alternatives_it_was_chosen_from() -> None:
    spec = _spec()
    _criterion(spec, "expr").alternatives = [
        ParameterAlternatives(param_name=_PERCENTILE, bound=["80"], option_count=3)
    ]

    replayed = _replayed(spec, _built(80), _built(48))

    assert _criterion(replayed, "expr").alternatives == []


def test_a_search_changed_outside_rebinds_the_criterion_to_it() -> None:
    rebound = _ast(
        combine(
            "c0",
            StrategyStepNode(id="text", search_name="GenesByText"),
            StrategyStepNode(
                id="expr",
                search_name="GenesByGoTerm",
                parameters={"go_term": StringValue(value="GO:0004672")},
            ),
        )
    )
    spec = _spec()
    _criterion(spec, "expr").defaulted_params = [_PERCENTILE]
    _criterion(spec, "expr").assumptions = [
        AssumedValue(param_name=_PERCENTILE, value="80", reason="ring stage")
    ]

    replayed = _replayed(spec, _built(80), rebound)

    criterion = _criterion(replayed, "expr")
    assert criterion.search_name == "GenesByGoTerm"
    assert criterion.resolved_params == {"go_term": StringValue(value="GO:0004672")}
    assert (criterion.defaulted_params, criterion.assumptions) == ([], [])


def test_a_step_deleted_outside_takes_its_criterion_out_of_the_spec() -> None:
    live = _ast(StrategyStepNode(id="text", search_name="GenesByText"))

    replayed = _replayed(_spec(), _built(), live)

    assert [c.id for c in replayed.criteria] == ["text"]
    assert structure_criteria(replayed.structure) == {"text"}


def test_an_emptied_strategy_leaves_the_spec_stating_nothing() -> None:
    replayed = _replayed(_spec(), _built(), None)

    assert replayed.criteria == []
    assert replayed.structure is None


def test_a_step_added_outside_is_stated_where_the_strategy_holds_it() -> None:
    grown = _ast(
        combine(
            "c1",
            combine(
                "c0",
                StrategyStepNode(id="text", search_name="GenesByText"),
                _expression(),
            ),
            StrategyStepNode(
                id="go",
                search_name="GenesByGoTerm",
                parameters={
                    "go_term": StringValue(value="GO:0004672"),
                    _HIDDEN: NumberValue(value=2),
                },
            ),
            operator=CombineOp.UNION,
        )
    )

    replayed = _replayed(_spec(), _built(), grown)

    assert structure_criteria(replayed.structure) == {"text", "expr", "go"}
    assert replayed.structure is not None
    assert replayed.structure.root.operator is CombineOp.UNION
    assert _criterion(replayed, "go").resolved_params == {
        "go_term": StringValue(value="GO:0004672")
    }


def test_an_operator_flipped_outside_is_the_operator_the_spec_states() -> None:
    flipped = _ast(
        combine(
            "c0",
            StrategyStepNode(id="text", search_name="GenesByText"),
            _expression(),
            operator=CombineOp.UNION,
        )
    )

    replayed = _replayed(_spec(), _built(), flipped)

    assert replayed.structure is not None
    assert replayed.structure.root.operator is CombineOp.UNION


def _with_a_pending_criterion(spec: OperationalSpec) -> OperationalSpec:
    """The plan a needs_user pass leaves: one criterion no step answers."""
    spec.criteria.append(
        Criterion(id="c_mass_spec", text="in the proteome", search_name="GenesByText")
    )
    assert spec.structure is not None
    spec.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[
                spec.structure.root,
                StructureNode(kind="leaf", criterion_id="c_mass_spec"),
            ],
        )
    )
    return spec


def test_a_pending_criterion_at_the_root_is_re_joined_over_the_live_tree() -> None:
    live = _ast(StrategyStepNode(id="text", search_name="GenesByText"))

    replayed = _replayed(_with_a_pending_criterion(_spec()), _built(), live)

    assert structure_criteria(replayed.structure) == {"text", "c_mass_spec"}
    assert [c.id for c in replayed.criteria] == ["text", "c_mass_spec"]


def test_a_pending_criterion_the_plan_nested_leaves_the_plan_alone() -> None:
    """Only a plan that hangs its pending criteria off its root combine is re-joined."""
    spec = _with_a_pending_criterion(_spec())
    assert spec.structure is not None
    spec.structure = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[
                StructureNode(kind="leaf", criterion_id="text"),
                StructureNode(
                    kind="combine",
                    operator=CombineOp.UNION,
                    inputs=[
                        StructureNode(kind="leaf", criterion_id="expr"),
                        StructureNode(kind="leaf", criterion_id="c_mass_spec"),
                    ],
                ),
            ],
        )
    )
    grown = _ast(
        combine(
            "c1",
            combine(
                "c0",
                StrategyStepNode(id="text", search_name="GenesByText"),
                _expression(),
            ),
            leaf("go", "GenesByGoTerm"),
        )
    )

    replayed = _replayed(spec, _built(), grown)

    assert replayed.structure == spec.structure
    assert "go" not in structure_criteria(replayed.structure)


def test_a_spec_the_strategy_still_answers_to_is_left_as_it_is() -> None:
    spec = _spec()

    replayed = _replayed(spec, _built(), _built())

    assert replayed == spec
