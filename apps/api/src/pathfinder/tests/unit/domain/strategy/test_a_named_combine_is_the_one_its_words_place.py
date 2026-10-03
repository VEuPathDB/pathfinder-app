"""A combine named by its place in the tree is that combine, and a tree that
moves any other combine breaks the request."""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.named_combine import (
    NamedCombine,
    combine_at,
    named_combine_breach,
)
from pathfinder.domain.strategy.operational_spec import SpecStructure, StructureNode

_EXPRESSION = "step_c341eba4"
_SIGNAL = "step_46ae849e"
_TM = "step_dff6f41b"


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _tree(outer: CombineOp, inner: CombineOp) -> SpecStructure:
    return SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=outer,
            inputs=[
                _leaf(_EXPRESSION),
                StructureNode(
                    kind="combine",
                    operator=inner,
                    inputs=[_leaf(_SIGNAL), _leaf(_TM)],
                ),
            ],
        )
    )


_FLIP_THE_LAST = (
    "Before I accept 39, flip the last combine - the one joining the surface "
    "features to blood-stage expression - to a UNION, and explain to me why "
    "the counts differ."
)


def test_the_last_combine_is_the_root_and_its_operator_is_stated() -> None:
    assert NamedCombine.read(_FLIP_THE_LAST) == NamedCombine(
        position="root", operator=CombineOp.UNION
    )


@pytest.mark.parametrize("word", ["final", "top", "outer", "root"])
def test_every_root_word_names_the_root(word: str) -> None:
    assert NamedCombine.read(f"make the {word} combine an intersection") == (
        NamedCombine(position="root", operator=CombineOp.INTERSECT)
    )


@pytest.mark.parametrize("word", ["first", "inner"])
def test_first_and_inner_name_the_deepest(word: str) -> None:
    assert NamedCombine.read(f"change the {word} combine to a union") == (
        NamedCombine(position="deepest", operator=CombineOp.UNION)
    )


@pytest.mark.parametrize(
    "message",
    [
        "Undo that, keep the intersection.",
        "flip the last combine",
        "flip the last combine to a union and the first combine to an intersection",
    ],
)
def test_a_message_without_one_placed_operator_names_no_combine(message: str) -> None:
    assert [NamedCombine.read(message)] == [None]


def test_the_root_and_the_deepest_combine_are_read_from_the_tree() -> None:
    tree = _tree(CombineOp.INTERSECT, CombineOp.UNION)

    root = combine_at(tree, "root")
    deepest = combine_at(tree, "deepest")

    assert root is tree.root
    assert deepest is tree.root.inputs[1]


def test_two_combines_at_the_deepest_level_name_no_combine() -> None:
    tree = SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.INTERSECT,
            inputs=[
                StructureNode(
                    kind="combine",
                    operator=CombineOp.UNION,
                    inputs=[_leaf("a"), _leaf("b")],
                ),
                StructureNode(
                    kind="combine",
                    operator=CombineOp.UNION,
                    inputs=[_leaf("c"), _leaf("d")],
                ),
            ],
        )
    )

    assert [combine_at(tree, "deepest")] == [None]


def test_a_tree_that_flips_the_inner_combine_breaks_the_named_root() -> None:
    named = NamedCombine(position="root", operator=CombineOp.UNION)
    held = _tree(CombineOp.INTERSECT, CombineOp.INTERSECT)

    breach = named_combine_breach(
        named, _tree(CombineOp.INTERSECT, CombineOp.UNION), held=held
    )

    assert breach is not None
    assert breach.required is CombineOp.UNION
    assert breach.built == "INTERSECT"
    assert breach.message == (
        "the user names the root combine, which must be UNION, but the tree "
        "joins it at INTERSECT"
    )


def test_a_tree_that_also_flips_another_combine_breaks_the_request() -> None:
    named = NamedCombine(position="root", operator=CombineOp.UNION)
    held = _tree(CombineOp.INTERSECT, CombineOp.INTERSECT)

    breach = named_combine_breach(
        named, _tree(CombineOp.UNION, CombineOp.UNION), held=held
    )

    assert breach is not None
    assert breach.built == "UNION"
    assert breach.message == (
        f"the user names only the root combine, but the tree moves the combine "
        f"over {_SIGNAL}, {_TM} from INTERSECT to UNION"
    )


def test_a_tree_that_flips_only_the_named_combine_stands() -> None:
    named = NamedCombine(position="root", operator=CombineOp.UNION)
    held = _tree(CombineOp.INTERSECT, CombineOp.INTERSECT)

    assert [
        named_combine_breach(
            named, _tree(CombineOp.UNION, CombineOp.INTERSECT), held=held
        )
    ] == [None]
