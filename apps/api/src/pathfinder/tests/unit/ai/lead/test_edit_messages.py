"""The edit work order prints the shape FRAME has to restate.

A pass that cannot see how the steps combine now cannot state a new nesting
over them, so it re-frames the goal instead of rewiring the strategy.
"""

from __future__ import annotations

from pathfinder.ai.lead.edit_messages import edit_work_order, unsupported_edit_message
from pathfinder.domain.parameters.values import MultiPickValue
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.ops import CombineOp


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="find proteases",
        criteria=[
            Criterion(
                id="step_text",
                text="protease text",
                search_name="GenesByText",
                role="seed",
                resolved_params={"organism": MultiPickValue(values=["Plasmodium"])},
            ),
            Criterion(id="step_go", text="proteolysis GO", search_name="GenesByGoTerm"),
            Criterion(
                id="step_expr", text="top decile", search_name="GenesByRNASeqEvidence"
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="step_text"),
                    StructureNode(
                        kind="combine",
                        operator=CombineOp.UNION,
                        inputs=[
                            StructureNode(kind="leaf", criterion_id="step_go"),
                            StructureNode(kind="leaf", criterion_id="step_expr"),
                        ],
                    ),
                ],
            )
        ),
    )


def _order() -> str:
    return edit_work_order(
        "union the two evidence branches", "union those two, then intersect", _spec()
    )


def test_the_work_order_prints_the_shape_the_strategy_has_now() -> None:
    lines = _order().splitlines()

    assert "  INTERSECT" in lines
    assert "    [step_text] protease text" in lines
    assert "    UNION" in lines
    assert "      [step_go] proteolysis GO" in lines


def test_a_transform_is_printed_with_the_step_it_consumes() -> None:
    spec = _spec()
    assert spec.structure is not None
    spec.criteria.append(
        Criterion(
            id="step_orth",
            text="P. vivax orthologs",
            search_name="GenesByOrthologs",
            role="transform",
        )
    )
    spec.structure = SpecStructure(
        root=StructureNode(
            kind="transform",
            criterion_id="step_orth",
            inputs=[spec.structure.root],
        )
    )

    lines = edit_work_order("map to orthologs", "map them", spec).splitlines()

    assert "  TRANSFORM [step_orth] P. vivax orthologs" in lines
    assert "    INTERSECT" in lines


def test_the_shape_is_printed_before_the_criteria_it_names() -> None:
    """The criteria block is parsed line by line, so nothing follows its values."""
    order = _order()

    assert order.index("INTERSECT") < order.index("- [step_text]")


def test_a_change_to_how_the_steps_combine_is_named_a_structure_change() -> None:
    order = " ".join(_order().split())

    assert "how the steps COMBINE is a structure change" in order
    assert "set_structure" in order
    assert "same criterion ids" in order


def test_the_refusal_names_the_invariant_and_not_a_missing_capability() -> None:
    message = unsupported_edit_message("the edit would strand ['step_go']")

    assert "the edit would strand ['step_go']" in message
    assert "re-nest" not in message
