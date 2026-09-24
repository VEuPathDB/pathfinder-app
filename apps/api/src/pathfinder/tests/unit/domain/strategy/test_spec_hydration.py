"""Reconstructing an OperationalSpec from the strategy that already exists.

The persisted AST holds the searches and the parameter values, so a thread
whose spec is missing can describe its own strategy without asking anyone.
"""

from __future__ import annotations

from veupathdb.domain.parameters import (
    MultiPickValue,
    NumberValue,
    StringValue,
)
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyAst,
    StrategyStepNode,
    walk,
)

from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
)
from pathfinder.domain.strategy.spec_hydration import (
    hidden_params_dropped,
    spec_from_ast,
)
from pathfinder.domain.strategy.spec_tree import (
    build_step_tree,
)


def _step_tree(spec: OperationalSpec) -> StrategyStepNode:
    return build_step_tree(spec).root


def _text_leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_text",
        search_name="GenesByText",
        parameters={"text_expression": StringValue(value="protease")},
        display_name="genes matching protease",
    )


def _taxon_leaf() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_taxon",
        search_name="GenesByTaxon",
        parameters={"organism": MultiPickValue(values=["Plasmodium"])},
        display_name="Plasmodium genes",
    )


def _expression_leaf(percentile: float) -> StrategyStepNode:
    return StrategyStepNode(
        id="step_expr",
        search_name="GenesByRNASeqEvidence",
        parameters={"min_expression_percentile": NumberValue(value=percentile)},
        display_name="highly expressed genes",
    )


def _three_leaf_ast(percentile: float = 90) -> StrategyAst:
    inner = StrategyStepNode(
        search_name=COMBINE_SEARCH_NAME,
        id="step_join1",
        operator=CombineOp.INTERSECT,
        primary_input=_text_leaf(),
        secondary_input=_taxon_leaf(),
    )
    root = StrategyStepNode(
        search_name=COMBINE_SEARCH_NAME,
        id="step_join2",
        operator=CombineOp.INTERSECT,
        primary_input=inner,
        secondary_input=_expression_leaf(percentile),
    )
    return StrategyAst(record_type="transcript", root=root, name="kinase hunt")


def _params_by_search(root: StrategyStepNode) -> dict[str, dict[str, object]]:
    return {
        node.search_name: dict(node.parameters)
        for node in walk(root)
        if node.search_name != COMBINE_SEARCH_NAME
    }


class TestTheValuesSurvive:
    def test_reconstructed_criteria_carry_the_hand_edited_value(self) -> None:
        spec = spec_from_ast(_three_leaf_ast(percentile=90), goal="find kinases")

        criterion = next(c for c in spec.criteria if c.id == "step_expr")
        assert criterion.resolved_params["min_expression_percentile"] == NumberValue(
            value=90
        )

    def test_the_parameters_are_copied_not_shared(self) -> None:
        ast = _three_leaf_ast()

        spec = spec_from_ast(ast, goal="g")

        criterion = next(c for c in spec.criteria if c.id == "step_taxon")
        criterion.resolved_params.pop("organism")
        assert "organism" in _params_by_search(ast.root)["GenesByTaxon"]

    def test_reconstructed_spec_is_buildable(self) -> None:
        ast = _three_leaf_ast()

        spec = spec_from_ast(ast, goal="find kinases")
        built = _params_by_search(_step_tree(spec))

        assert built == _params_by_search(ast.root)


class TestTheCriteriaAddressTheSteps:
    def test_criterion_ids_are_step_ids(self) -> None:
        spec = spec_from_ast(_three_leaf_ast(), goal="g")

        assert {c.id for c in spec.criteria} == {
            "step_text",
            "step_taxon",
            "step_expr",
        }

    def test_combine_node_produces_no_criterion(self) -> None:
        spec = spec_from_ast(_three_leaf_ast(), goal="g")

        assert len(spec.criteria) == 3

    def test_a_combine_node_carries_its_operator_and_no_criterion_id(self) -> None:
        spec = spec_from_ast(_three_leaf_ast(), goal="g")

        assert spec.structure is not None
        root = spec.structure.root
        assert root.kind == "combine"
        assert root.operator == CombineOp.INTERSECT
        assert root.criterion_id is None


class TestTheRolesFollowTheTree:
    def test_transform_role_is_derived_from_one_input(self) -> None:
        root = StrategyStepNode(
            id="step_ortho",
            search_name="GenesByOrthologs",
            parameters={"organism": MultiPickValue(values=["Pvivax"])},
            primary_input=_text_leaf(),
        )
        ast = StrategyAst(record_type="transcript", root=root)

        spec = spec_from_ast(ast, goal="g")

        criterion = next(c for c in spec.criteria if c.id == "step_ortho")
        assert criterion.role == "transform"
        assert spec.structure is not None
        assert spec.structure.root.kind == "transform"
        assert spec.structure.root.criterion_id == "step_ortho"
        assert spec.structure.root.inputs[0].criterion_id == "step_text"

    def test_the_deepest_primary_leaf_is_the_seed(self) -> None:
        spec = spec_from_ast(_three_leaf_ast(), goal="g")

        by_id = {c.id: c.role for c in spec.criteria}
        assert by_id["step_text"] == "seed"
        assert by_id["step_taxon"] == "filter"
        assert by_id["step_expr"] == "filter"


class TestTheReconstructionClaimsNothingItCannotKnow:
    def test_reconstruction_asserts_no_provenance(self) -> None:
        spec = spec_from_ast(_three_leaf_ast(), goal="g")

        assert all(not c.defaulted_params for c in spec.criteria)
        assert all(c.confidence == 0.0 for c in spec.criteria)
        assert all(not c.open_params for c in spec.criteria)
        assert spec.open_slots == []
        assert spec.dropped == []

    def test_the_text_is_the_display_name(self) -> None:
        spec = spec_from_ast(_three_leaf_ast(), goal="g")

        criterion = next(c for c in spec.criteria if c.id == "step_taxon")
        assert criterion.text == "Plasmodium genes"

    def test_a_node_without_a_display_name_is_labelled_by_its_search(self) -> None:
        root = StrategyStepNode(id="step_a", search_name="GenesByTaxon")
        ast = StrategyAst(record_type="transcript", root=root)

        spec = spec_from_ast(ast, goal="g")

        assert spec.criteria[0].text == "GenesByTaxon step"

    def test_the_record_type_and_goal_come_through(self) -> None:
        spec = spec_from_ast(_three_leaf_ast(), goal="find kinases")

        assert spec.record_type == "transcript"
        assert spec.goal == "find kinases"
        assert spec.title == "kinase hunt"

    def test_a_single_leaf_strategy_reconstructs_as_a_seed(self) -> None:
        ast = StrategyAst(
            record_type="transcript",
            root=StrategyStepNode(id="step_only", search_name="GenesByTaxon"),
        )

        spec = spec_from_ast(ast, goal="g")

        assert [c.role for c in spec.criteria] == ["seed"]
        assert spec.structure is not None
        assert spec.structure.root.kind == "leaf"


class TestTheSheetDecidesWhichParamsTheSpecStates:
    def test_a_parameter_the_sheet_hides_is_not_stated(self) -> None:
        root = StrategyStepNode(
            id="step_7c2e770b",
            search_name="GenesByRNASeqpfal3D7_Su_seven_stages_rnaSeq_RSRC",
            parameters={
                "profileset_generic": StringValue(value="Pfal3D7 Su seven stages"),
                "dataset_url": StringValue(
                    value="https://PlasmoDB.org/a/app/record/dataset/DS_66f9e70b8a"
                ),
            },
        )
        ast = StrategyAst(record_type="transcript", root=root)

        spec = hidden_params_dropped(
            spec_from_ast(ast, goal="g"),
            sheet_params={
                "GenesByRNASeqpfal3D7_Su_seven_stages_rnaSeq_RSRC": frozenset(
                    {"profileset_generic"}
                )
            },
        )

        criterion = spec.criteria[0]
        assert "dataset_url" not in criterion.resolved_params
        assert criterion.resolved_params["profileset_generic"] == StringValue(
            value="Pfal3D7 Su seven stages"
        )

    def test_a_search_the_mapping_does_not_name_keeps_its_values(self) -> None:
        spec = hidden_params_dropped(
            spec_from_ast(_three_leaf_ast(), goal="g"), sheet_params={}
        )

        criterion = next(c for c in spec.criteria if c.id == "step_taxon")
        assert criterion.resolved_params["organism"] == MultiPickValue(
            values=["Plasmodium"]
        )

    def test_the_hydrated_spec_is_left_alone(self) -> None:
        hydrated = spec_from_ast(_three_leaf_ast(), goal="g")

        hidden_params_dropped(hydrated, sheet_params={"GenesByTaxon": frozenset()})

        criterion = next(c for c in hydrated.criteria if c.id == "step_taxon")
        assert "organism" in criterion.resolved_params
