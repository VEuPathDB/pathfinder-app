"""A combine no researcher named carries the name of its operator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepKind,
    StrategyStep,
    StrategyStepNode,
)

from pathfinder.domain.strategy.combine_naming import (
    combine_display_name,
    combine_name,
    name_the_combines,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    build_step_tree,
)
from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    DuplicateStepOp,
    UpdateCombineOperatorOp,
)
from pathfinder.domain.strategy.operations.apply import apply_operation

from ._builders import (
    graph_of,
    plan,
    spec_joined,
    spec_leaf,
    spec_of,
    three_step_root,
)

_PARITY = (
    Path(__file__).resolve().parents[8] / "packages" / "spec" / "operations_parity.json"
)
_WDK_DEFAULT = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


def test_every_operator_has_the_label_the_canvas_shows() -> None:
    labels = json.loads(_PARITY.read_text())["combine_labels"]

    assert {op.value: combine_display_name(op) for op in CombineOp} == labels


@pytest.mark.parametrize(
    ("name", "search_name", "expected"),
    [
        (None, COMBINE_SEARCH_NAME, "Union"),
        ("", COMBINE_SEARCH_NAME, "Union"),
        (_WDK_DEFAULT, _WDK_DEFAULT, "Union"),
        ("Intersect", COMBINE_SEARCH_NAME, "Union"),
        ("INTERSECT combine", COMBINE_SEARCH_NAME, "Union"),
        ("rminus Combine", COMBINE_SEARCH_NAME, "Union"),
        ("Intersect kinases combine", COMBINE_SEARCH_NAME, "Intersect kinases combine"),
        (
            "Kinases not in the apicoplast",
            COMBINE_SEARCH_NAME,
            "Kinases not in the apicoplast",
        ),
    ],
)
def test_only_a_name_a_researcher_gave_survives(
    name: str | None, search_name: str, expected: str
) -> None:
    assert combine_name(name, search_name, CombineOp.UNION) == expected


def test_a_step_with_no_operator_keeps_its_name() -> None:
    assert combine_name("GenesByTaxon", "GenesByTaxon", None) == "GenesByTaxon"


def _built_combine(operator: CombineOp) -> StrategyStepNode:
    spec = OperationalSpec(
        goal="g",
        criteria=[
            Criterion(id="c1", text="kinase", search_name="GenesByText"),
            Criterion(id="c2", text="secreted", search_name="GenesBySignalPeptide"),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=operator,
                inputs=[spec_leaf("c1"), spec_leaf("c2")],
            )
        ),
    )
    return build_step_tree(spec).root


@pytest.mark.parametrize("operator", [CombineOp.INTERSECT, CombineOp.MINUS])
def test_a_built_combine_carries_its_operators_name(operator: CombineOp) -> None:
    assert _built_combine(operator).display_name == combine_display_name(operator)


def test_an_added_combine_carries_its_operators_name() -> None:
    root = three_step_root()
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.criteria.append(
        Criterion(id="c_new", text="secreted", search_name="GenesBySignalPeptide")
    )
    assert before.structure is not None
    after.structure = SpecStructure(
        root=spec_joined(
            CombineOp.UNION,
            before.structure.root.model_copy(deep=True),
            spec_leaf("c_new"),
        )
    )

    ops = plan(before, after, graph_of(root))

    added = [op for op in ops if isinstance(op, AddCombineOp)]
    assert [op.step.display_name for op in added] == ["Union"]


def test_a_rearranged_combine_takes_the_name_of_its_new_operator() -> None:
    root = three_step_root()
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.structure = SpecStructure(
        root=spec_joined(
            CombineOp.UNION,
            spec_leaf("step_expr"),
            spec_joined(CombineOp.MINUS, spec_leaf("step_text"), spec_leaf("step_go")),
        )
    )

    graph = graph_of(root)
    for op in plan(before, after, graph):
        apply_operation(graph, op)

    assert graph.steps["step_c1"].display_name == "Minus"


def test_an_operator_change_renames_a_combine_no_researcher_named() -> None:
    graph = graph_of(three_step_root())
    graph.steps["step_c1"].display_name = "Intersect"

    apply_operation(
        graph, UpdateCombineOperatorOp(step_id="step_c1", operator=CombineOp.UNION)
    )

    assert graph.steps["step_c1"].display_name == "Union"


def test_an_operator_change_renames_a_name_the_canvas_generated() -> None:
    graph = graph_of(three_step_root())
    graph.steps["step_c1"].display_name = "INTERSECT combine"

    apply_operation(
        graph, UpdateCombineOperatorOp(step_id="step_c1", operator=CombineOp.UNION)
    )

    assert graph.steps["step_c1"].display_name == "Union"


def test_an_operator_change_keeps_a_researchers_name() -> None:
    graph = graph_of(three_step_root())
    graph.steps["step_c1"].display_name = "Proteases in both"

    apply_operation(
        graph, UpdateCombineOperatorOp(step_id="step_c1", operator=CombineOp.UNION)
    )

    assert graph.steps["step_c1"].display_name == "Proteases in both"


def test_an_unnamed_added_combine_takes_its_operators_name() -> None:
    graph = graph_of(three_step_root())

    apply_operation(
        graph,
        AddCombineOp(
            step=StrategyStepNode(
                id="step_new",
                search_name=COMBINE_SEARCH_NAME,
                operator=CombineOp.RMINUS,
            ),
            left_id="step_c2",
            right_id="step_text",
        ),
    )

    assert graph.steps["step_new"].display_name == "Minus (reversed)"


def test_a_duplicate_is_joined_under_the_intersect_name() -> None:
    graph = graph_of(three_step_root())

    apply_operation(
        graph,
        DuplicateStepOp(
            source_step_id="step_text",
            duplicate_step_id="step_dup",
            combine_step_id="step_join",
        ),
    )

    assert graph.steps["step_join"].display_name == "Intersect"


def test_every_unnamed_combine_is_named() -> None:
    steps = [
        StrategyStep(id="a", kind=StepKind.SEARCH, search_name="GenesByText"),
        StrategyStep(id="c1", kind=StepKind.COMBINE, operator=CombineOp.INTERSECT),
        StrategyStep(
            id="c2",
            kind=StepKind.COMBINE,
            search_name=_WDK_DEFAULT,
            display_name=_WDK_DEFAULT,
            operator=CombineOp.UNION,
        ),
        StrategyStep(
            id="c4",
            kind=StepKind.COMBINE,
            display_name="INTERSECT combine",
            operator=CombineOp.UNION,
        ),
        StrategyStep(
            id="c3",
            kind=StepKind.COMBINE,
            display_name="Kept",
            operator=CombineOp.MINUS,
        ),
    ]

    name_the_combines(steps)

    assert [step.display_name for step in steps] == [
        None,
        "Intersect",
        "Union",
        "Union",
        "Kept",
    ]
