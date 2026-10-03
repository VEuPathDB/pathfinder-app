"""Each kind of structure node takes one shape, and the type refuses any other."""

from __future__ import annotations

import re
from typing import Any

import pytest
from pydantic import ValidationError
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.operational_spec import SpecStructure, StructureNode

_LEAF: dict[str, Any] = {"kind": "leaf", "criterionId": "c_secreted"}
_OTHER_LEAF: dict[str, Any] = {"kind": "leaf", "criterionId": "c_kinase"}


def _refusal(raw: dict[str, Any]) -> str:
    with pytest.raises(ValidationError) as refused:
        StructureNode.model_validate(raw)
    (error,) = refused.value.errors()
    return str(error["msg"])


@pytest.mark.parametrize(
    "raw",
    [
        _LEAF,
        {
            "kind": "combine",
            "operator": "INTERSECT",
            "inputs": [_LEAF, _OTHER_LEAF],
        },
        {
            "kind": "combine",
            "operator": "UNION",
            "inputs": [_LEAF, _OTHER_LEAF, {"kind": "leaf", "criterionId": "c_gpi"}],
        },
        {"kind": "transform", "criterionId": "c_orthologs", "inputs": [_LEAF]},
        {"kind": "copy", "inputs": [_LEAF]},
    ],
)
def test_each_kind_in_its_shape_is_accepted(raw: dict[str, Any]) -> None:
    node = StructureNode.model_validate(raw)

    assert node.kind == raw["kind"]
    assert len(node.inputs) == len(raw.get("inputs", []))


def test_a_leaf_without_a_criterion_is_refused() -> None:
    message = _refusal({"kind": "leaf"})

    assert message == (
        'Value error, a leaf is {"kind": "leaf", "criterionId": "<id>"}: one '
        "bound criterion, with no inputs and no operator."
    )


@pytest.mark.parametrize(
    "raw",
    [
        {**_LEAF, "inputs": [_OTHER_LEAF]},
        {**_LEAF, "operator": "INTERSECT"},
    ],
)
def test_a_leaf_with_inputs_or_an_operator_is_refused(raw: dict[str, Any]) -> None:
    assert _refusal(raw).startswith('Value error, a leaf is {"kind": "leaf"')


def test_a_combine_of_no_inputs_is_refused() -> None:
    message = _refusal({"kind": "combine", "operator": "INTERSECT", "inputs": []})

    assert message == (
        'Value error, a combine is {"kind": "combine", "operator": "INTERSECT" | '
        '"UNION" | "MINUS", "inputs": [<left>, <right>]}: an operator over two or '
        "more subtrees, with no criterionId. A tree of one criterion is that "
        "criterion's leaf; with no criterion left, there is no tree to set."
    )


@pytest.mark.parametrize(
    "raw",
    [
        {"kind": "combine", "inputs": [_LEAF, _OTHER_LEAF]},
        {
            "kind": "combine",
            "operator": "INTERSECT",
            "criterionId": "c_secreted",
            "inputs": [_LEAF, _OTHER_LEAF],
        },
    ],
)
def test_a_combine_without_an_operator_or_with_a_criterion_is_refused(
    raw: dict[str, Any],
) -> None:
    assert _refusal(raw).startswith('Value error, a combine is {"kind": "combine"')


@pytest.mark.parametrize(
    "raw",
    [
        {"kind": "transform", "inputs": [_LEAF]},
        {"kind": "transform", "criterionId": "c_orthologs"},
        {
            "kind": "transform",
            "criterionId": "c_orthologs",
            "inputs": [_LEAF, _OTHER_LEAF],
        },
        {
            "kind": "transform",
            "criterionId": "c_orthologs",
            "operator": "UNION",
            "inputs": [_LEAF],
        },
    ],
)
def test_a_transform_off_its_shape_is_refused(raw: dict[str, Any]) -> None:
    assert _refusal(raw) == (
        'Value error, a transform is {"kind": "transform", "criterionId": "<id>", '
        '"inputs": [<subtree>]}: one criterion that maps exactly one input '
        "subtree, with no operator."
    )


@pytest.mark.parametrize(
    "raw",
    [
        {"kind": "copy"},
        {"kind": "copy", "inputs": [_LEAF, _OTHER_LEAF]},
        {"kind": "copy", "criterionId": "c_secreted", "inputs": [_LEAF]},
        {"kind": "copy", "operator": "INTERSECT", "inputs": [_LEAF]},
    ],
)
def test_a_copy_off_its_shape_is_refused(raw: dict[str, Any]) -> None:
    assert _refusal(raw) == (
        'Value error, a copy is {"kind": "copy", "inputs": [<subtree>]}: exactly '
        "one subtree the tree already states, with no criterionId and no operator."
    )


def test_a_structure_refuses_an_intersect_of_nothing() -> None:
    with pytest.raises(ValidationError) as refused:
        SpecStructure.model_validate(
            {"root": {"kind": "combine", "operator": "INTERSECT", "inputs": []}}
        )

    (error,) = refused.value.errors()
    assert error["loc"] == ("root",)
    assert 'a combine is {"kind": "combine"' in str(error["msg"])


def test_a_nested_combine_of_no_inputs_is_refused_where_it_stands() -> None:
    with pytest.raises(ValidationError) as refused:
        StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            inputs=[
                StructureNode.model_validate(_LEAF),
                StructureNode.model_validate(
                    {"kind": "combine", "operator": "MINUS", "inputs": []}
                ),
            ],
        )

    assert "a combine is" in str(refused.value)


def test_the_operator_and_the_criterion_read_from_their_kinds() -> None:
    combine = StructureNode.model_validate(
        {"kind": "combine", "operator": "MINUS", "inputs": [_LEAF, _OTHER_LEAF]}
    )

    assert combine.combine_operator is CombineOp.MINUS
    assert combine.inputs[0].named_criterion == "c_secreted"


def test_a_node_built_without_validation_names_the_shape_it_lacks() -> None:
    unchecked = StructureNode.model_construct(kind="leaf", criterion_id=None)

    with pytest.raises(ValueError, match=re.escape('a leaf is {"kind": "leaf"')):
        _ = unchecked.named_criterion
    with pytest.raises(ValueError, match=re.escape('a leaf is {"kind": "leaf"')):
        _ = unchecked.combine_operator
