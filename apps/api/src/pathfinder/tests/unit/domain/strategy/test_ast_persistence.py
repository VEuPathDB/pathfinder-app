"""The exact JSON a strategy is persisted and served as, and the clone that
gives a reused subtree fresh ids.

Every stored conversation and every OpenAPI response carries this shape, so a
key that moves here is a migration.
"""

from __future__ import annotations

from assistant_core.platform.types import JSONObject
from hypothesis import given

from pathfinder.domain.parameters.values import MultiPickValue, StringValue
from pathfinder.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from pathfinder.domain.strategy.graph_model import flatten_tree, rebuild_tree
from pathfinder.domain.strategy.ops import CombineOp
from pathfinder.domain.strategy.strategy_ast import StrategyAst
from pathfinder.domain.strategy.tree import clone_with_fresh_ids, walk

from ._builders import ANY_TREE, PROFILE

_BOOLEAN_QUESTION = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


def _fixture() -> StrategyAst:
    """One node of each kind, a detached root, and a WDK-named combine."""
    return StrategyAst(
        record_type="transcript",
        name="kinases",
        root=StrategyStepNode(
            id="c",
            search_name=COMBINE_SEARCH_NAME,
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(
                id="t",
                search_name="GenesByOrthologs",
                primary_input=StrategyStepNode(
                    id="a",
                    search_name="GenesByText",
                    parameters={"text_expression": StringValue(value="kinase")},
                ),
            ),
            secondary_input=StrategyStepNode(
                id="imported",
                search_name=_BOOLEAN_QUESTION,
                operator=CombineOp.UNION,
                primary_input=StrategyStepNode(id="b", search_name="GenesByTaxon"),
                secondary_input=StrategyStepNode(
                    id="d",
                    search_name="GenesByGoTerm",
                    parameters={"go_term": MultiPickValue(values=["GO:0004672"])},
                ),
            ),
        ),
        detached_roots=[StrategyStepNode(id="z", search_name="GenesBySignalPeptide")],
    )


_LEAF_DEFAULTS: JSONObject = {
    "parameters": {},
    "filters": [],
    "analyses": [],
    "reports": [],
}

_EXPECTED: JSONObject = {
    "recordType": "transcript",
    "name": "kinases",
    "root": {
        "id": "c",
        "searchName": "__combine__",
        "operator": "INTERSECT",
        **_LEAF_DEFAULTS,
        "primaryInput": {
            "id": "t",
            "searchName": "GenesByOrthologs",
            **_LEAF_DEFAULTS,
            "primaryInput": {
                "id": "a",
                "searchName": "GenesByText",
                **_LEAF_DEFAULTS,
                "parameters": {
                    "text_expression": {"type": "string", "value": "kinase"}
                },
            },
        },
        "secondaryInput": {
            "id": "imported",
            "searchName": _BOOLEAN_QUESTION,
            "operator": "UNION",
            **_LEAF_DEFAULTS,
            "primaryInput": {
                "id": "b",
                "searchName": "GenesByTaxon",
                **_LEAF_DEFAULTS,
            },
            "secondaryInput": {
                "id": "d",
                "searchName": "GenesByGoTerm",
                **_LEAF_DEFAULTS,
                "parameters": {
                    "go_term": {
                        "type": "multi-pick-vocabulary",
                        "values": ["GO:0004672"],
                    }
                },
            },
        },
    },
    "detachedRoots": [
        {"id": "z", "searchName": "GenesBySignalPeptide", **_LEAF_DEFAULTS},
    ],
}


class TestThePersistedShape:
    def test_the_fixture_serializes_to_the_pinned_json(self) -> None:
        dumped = _fixture().model_dump(by_alias=True, exclude_none=True, mode="json")

        assert dumped == _EXPECTED

    def test_the_json_parses_back_to_the_same_model(self) -> None:
        ast = _fixture()

        assert StrategyAst.model_validate(ast.model_dump(by_alias=True)) == ast

    def test_the_flat_split_and_rejoin_is_the_identity(self) -> None:
        root = _fixture().root

        assert rebuild_tree(root.id, flatten_tree(root)) == root

    def test_an_imported_combine_keeps_its_wdk_question_name(self) -> None:
        """A combine WDK named is not the sentinel, and the name survives."""
        steps = flatten_tree(_fixture().root)

        assert steps["imported"].search_name == _BOOLEAN_QUESTION
        assert steps["c"].search_name is None
        assert rebuild_tree("c", steps).search_name == COMBINE_SEARCH_NAME


@PROFILE
@given(ANY_TREE)
def test_strategy_ast_json_round_trip_is_identity(root: StrategyStepNode) -> None:
    original = StrategyAst(record_type="transcript", root=root)
    restored = StrategyAst.model_validate_json(original.model_dump_json(by_alias=True))
    assert original == restored
    assert original.model_dump(by_alias=True) == restored.model_dump(by_alias=True)


@PROFILE
@given(ANY_TREE)
def test_strategy_ast_python_round_trip_is_identity(root: StrategyStepNode) -> None:
    original = StrategyAst(record_type="transcript", root=root)
    assert StrategyAst.model_validate(original.model_dump(by_alias=True)) == original


def _combine_subtree() -> StrategyStepNode:
    return StrategyStepNode(
        id="step_combine",
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=StrategyStepNode(
            id="step_taxon",
            search_name="GenesByTaxon",
            parameters={
                "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
            },
        ),
        secondary_input=StrategyStepNode(
            id="step_text",
            search_name="GenesByText",
            parameters={"text_expression": StringValue(value="invasion")},
        ),
    )


class TestCloneWithFreshIds:
    """A cloned subtree never shares ids or parameter dicts with its source."""

    def test_clone_assigns_fresh_ids_to_every_node(self) -> None:
        src = _combine_subtree()
        clone = clone_with_fresh_ids(src)

        src_ids = {n.id for n in walk(src)}
        clone_ids = {n.id for n in walk(clone)}
        assert len(clone_ids) == 3
        assert src_ids.isdisjoint(clone_ids), "clone reused a source step id"

    def test_clone_preserves_topology_operator_and_params(self) -> None:
        clone = clone_with_fresh_ids(_combine_subtree())

        assert clone.search_name == COMBINE_SEARCH_NAME
        assert clone.operator == CombineOp.INTERSECT
        assert clone.primary_input is not None
        assert clone.secondary_input is not None
        assert clone.primary_input.search_name == "GenesByTaxon"
        assert clone.primary_input.parameters["organism"] == MultiPickValue(
            values=["Plasmodium falciparum 3D7"],
        )
        assert clone.secondary_input.search_name == "GenesByText"
        assert clone.secondary_input.parameters["text_expression"] == StringValue(
            value="invasion",
        )

    def test_clone_parameters_dict_is_isolated_from_source(self) -> None:
        """``model_copy`` is shallow, so a shared dict would let an edit on the
        clone reach the source step."""
        src = _combine_subtree()
        clone = clone_with_fresh_ids(src)

        assert clone.primary_input is not None
        assert src.primary_input is not None
        assert clone.primary_input.parameters is not src.primary_input.parameters, (
            "clone shares the source node's parameters dict object (shallow copy)"
        )

        clone.primary_input.parameters["added_on_clone"] = StringValue(value="x")
        assert "added_on_clone" not in src.primary_input.parameters, (
            "mutating the clone's parameters dict leaked into the source step"
        )
