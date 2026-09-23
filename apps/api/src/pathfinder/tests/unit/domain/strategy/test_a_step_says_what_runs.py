"""A step is titled by the search it runs, and keeps the researcher's words."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import CombineOp, StrategyAst

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    build_step_tree,
)
from pathfinder.domain.strategy.operations import AddLeafOp, ReplaceSubtreeOp
from pathfinder.domain.strategy.spec_hydration import spec_from_ast
from pathfinder.domain.strategy.step_words import (
    AddedSearch,
    StepWords,
    added_searches,
    criterion_texts,
)

from ._builders import (
    graph_of,
    plan,
    spec_joined,
    spec_leaf,
    spec_of,
    spec_transform,
    three_step_root,
)

_EXPORTED = Criterion(
    id="c_gpi",
    text="genes with a predicted GPI anchor",
    search_name="GenesByExportPrediction",
    search_display_name="Exported Protein",
)
_ORTHOLOGS = Criterion(
    id="c_orth",
    text="their P. vivax orthologs",
    search_name="GenesByOrthologs",
    role="transform",
    search_display_name="Orthologs",
)


def _spec(*criteria: Criterion, root: StructureNode) -> OperationalSpec:
    return OperationalSpec(
        goal="g", criteria=list(criteria), structure=SpecStructure(root=root)
    )


def test_a_built_leaf_is_titled_by_its_search() -> None:
    root = build_step_tree(_spec(_EXPORTED, root=spec_leaf("c_gpi"))).root

    assert root.display_name == "Exported Protein"


def test_a_built_transform_is_titled_by_its_search() -> None:
    spec = _spec(
        _EXPORTED, _ORTHOLOGS, root=spec_transform("c_orth", spec_leaf("c_gpi"))
    )

    root = build_step_tree(spec).root

    assert (
        root.display_name,
        root.primary_input and root.primary_input.display_name,
    ) == (
        "Orthologs",
        "Exported Protein",
    )


def test_a_criterion_with_no_known_search_name_keeps_its_words() -> None:
    bare = _EXPORTED.model_copy(update={"search_display_name": None})

    root = build_step_tree(_spec(bare, root=spec_leaf("c_gpi"))).root

    assert root.display_name == "genes with a predicted GPI anchor"


def test_a_leaf_an_edit_adds_is_titled_by_its_search() -> None:
    root = three_step_root()
    before = spec_of(root)
    after = before.model_copy(deep=True)
    after.criteria.append(_EXPORTED)
    assert before.structure is not None
    after.structure = SpecStructure(
        root=spec_joined(
            CombineOp.INTERSECT,
            before.structure.root.model_copy(deep=True),
            spec_leaf("c_gpi"),
        )
    )

    ops = plan(before, after, graph_of(root))

    added = [op.step.display_name for op in ops if isinstance(op, AddLeafOp)]
    assert added == ["Exported Protein"]


def _restated_title(after: OperationalSpec, renamed: str) -> str | None:
    root = three_step_root()
    before = spec_of(root)
    graph = graph_of(root)
    graph.steps["step_text"].display_name = renamed
    ops = plan(before, after, graph)
    subtrees = [op.subtree for op in ops if isinstance(op, ReplaceSubtreeOp)]
    assert [s.id for s in subtrees] == ["step_text"]
    return subtrees[0].display_name


def test_a_restated_step_keeps_the_name_a_researcher_gave_it() -> None:
    after = spec_of(three_step_root())
    text = next(c for c in after.criteria if c.id == "step_text")
    text.resolved_params = {}

    assert _restated_title(after, "My proteases") == "My proteases"


def test_a_rebound_step_takes_the_name_of_its_new_search() -> None:
    after = spec_of(three_step_root())
    text = next(c for c in after.criteria if c.id == "step_text")
    text.search_name = "GenesByExportPrediction"
    text.search_display_name = "Exported Protein"
    text.resolved_params = {"organism": MultiPickValue(values=["Plasmodium"])}

    assert _restated_title(after, "My proteases") == "Exported Protein"


def test_the_graph_carries_the_researchers_words_through_its_ast() -> None:
    graph = graph_of(three_step_root())

    graph.note_criteria({"step_text": "protease genes", "step_gone": "stale words"})
    ast = graph.to_strategy_ast()

    assert ast is not None
    assert StepWords.of(ast).criterion_texts == {"step_text": "protease genes"}


def test_a_graph_with_no_words_writes_no_metadata() -> None:
    ast = graph_of(three_step_root()).to_strategy_ast()

    assert ast is not None
    assert (ast.metadata, StepWords.of(ast).criterion_texts) == (None, {})


def test_a_hydrated_criterion_states_the_researchers_words() -> None:
    graph = graph_of(three_step_root())
    graph.note_criteria({"step_text": "protease genes"})
    ast = graph.to_strategy_ast()
    assert isinstance(ast, StrategyAst)

    texts = {c.id: c.text for c in spec_from_ast(ast, goal="g").criteria}

    assert (texts["step_text"], texts["step_go"]) == (
        "protease genes",
        "proteolysis GO",
    )


def test_the_words_are_keyed_by_the_step_each_criterion_built() -> None:
    spec = _spec(
        _EXPORTED, _ORTHOLOGS, root=spec_transform("c_orth", spec_leaf("c_gpi"))
    )

    texts = criterion_texts(spec, {"c_gpi": "step_1", "c_orth": "step_2"})

    assert texts == {
        "step_1": "genes with a predicted GPI anchor",
        "step_2": "their P. vivax orthologs",
    }


def test_an_added_search_names_what_runs_and_what_it_stands_for() -> None:
    spec = _spec(
        _EXPORTED, _ORTHOLOGS, root=spec_transform("c_orth", spec_leaf("c_gpi"))
    )

    assert added_searches(spec, {"c_gpi"}) == [
        AddedSearch(
            step_id="c_gpi",
            search_display_name="Exported Protein",
            criterion_text="genes with a predicted GPI anchor",
        )
    ]
