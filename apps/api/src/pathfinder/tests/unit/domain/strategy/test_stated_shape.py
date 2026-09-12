"""The leaf-set invariant every strategy write holds."""

from __future__ import annotations

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepKind,
    StrategyStepNode,
)

from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SavedStrategyRef,
    SpecStructure,
    build_step_tree,
    renumber_criteria,
)
from pathfinder.domain.strategy.operations import (
    AddLeafOp,
    ReplaceSubtreeOp,
    WireInputOp,
)
from pathfinder.domain.strategy.operations.types import (
    AttachIntoSlot,
    AttachNewRoot,
    GraphOperation,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.stated_shape import (
    SlotWrite,
    evicted_by,
    overwritten_slot,
    placeholder_names,
    shape_after,
    stated_shape,
)

from ._builders import (
    combine,
    graph_with,
    leaf,
    spec_joined,
    spec_leaf,
    transform,
)


def test_the_stated_criteria_are_the_non_combine_steps() -> None:
    graph = graph_with([combine("c", leaf("a"), transform("t", leaf("b")))])

    shape = stated_shape(
        graph=graph, root_id="c", criteria={"a", "b", "t"}, outside=set()
    )

    assert shape.searches == ("a", "b", "t")
    assert shape.holds is True


def test_a_criterion_with_no_step_is_reported_lost() -> None:
    graph = graph_with([combine("c", leaf("a"), leaf("b"))])

    shape = stated_shape(
        graph=graph, root_id="c", criteria={"a", "b", "gone"}, outside=set()
    )

    assert shape.lost == ("gone",)
    assert shape.unstated == ()
    assert shape.holds is False


def test_a_step_no_criterion_states_is_reported_unstated() -> None:
    graph = graph_with([combine("c", leaf("a"), leaf("b"))])

    shape = stated_shape(graph=graph, root_id="c", criteria={"a"}, outside=set())

    assert shape.unstated == ("b",)
    assert shape.holds is False


def test_a_step_outside_the_strategy_is_neither_adopted_nor_stranded() -> None:
    graph = graph_with([combine("c", leaf("a"), leaf("b")), leaf("detached")])

    shape = stated_shape(
        graph=graph, root_id="c", criteria={"a", "b"}, outside={"detached"}
    )

    assert shape.adopted == ()
    assert shape.stranded == ()
    assert shape.holds is True


def test_the_shape_of_a_write_leaves_the_live_graph_alone() -> None:
    graph = graph_with([combine("c", leaf("a"), leaf("b"))])
    op = ReplaceSubtreeOp(step_id="a", subtree=leaf("replacement"))

    shape = shape_after(op, graph=graph, criteria={"a", "b"})

    assert shape.lost == ("a",)
    assert shape.unstated == ("replacement",)
    assert set(graph.steps) == {"a", "b", "c"}


def test_a_write_that_keeps_every_criterion_holds() -> None:
    graph = graph_with([combine("c", leaf("a"), leaf("b"))])
    op = ReplaceSubtreeOp(step_id="a", subtree=leaf("a", search_name="geneByLocusTag"))

    shape = shape_after(op, graph=graph, criteria={"a", "b"})

    assert shape.holds is True


def test_a_placeholder_name_is_found_and_the_combine_sentinel_is_not() -> None:
    tree = combine("c", leaf("a", search_name="__input_step__"), leaf("b"))

    assert placeholder_names(tree) == ("__input_step__",)


def test_a_tree_of_real_searches_carries_no_placeholder() -> None:
    tree = combine("c", leaf("a"), transform("t", leaf("b")))

    assert placeholder_names(tree) == ()


def _spec_over_a_saved_strategy() -> OperationalSpec:
    """One InterPro leaf intersected with a saved strategy of two searches."""
    saved = combine(
        "saved_root",
        leaf("saved_a", search_name="GenesByGoTerm"),
        leaf("saved_b", search_name="GenesByText"),
        operator=CombineOp.UNION,
    )
    return OperationalSpec(
        goal="kinases",
        criteria=[
            Criterion(
                id="c1", text="InterPro kinase domain", search_name="GenesByInterpro"
            ),
            Criterion(
                id="c2",
                text="the saved kinase strategy",
                saved_strategy_ref=SavedStrategyRef(
                    conversation_id="conv",
                    name="kinases",
                    wdk_strategy_id=999,
                    step_count=3,
                    subtree=saved,
                ),
            ),
        ],
        structure=SpecStructure(
            root=spec_joined(CombineOp.INTERSECT, spec_leaf("c1"), spec_leaf("c2"))
        ),
    )


def _built_over_a_saved_strategy() -> tuple[StrategyGraph, set[str]]:
    """The graph a saved-strategy spec builds, and the criterion ids it minted."""
    spec = _spec_over_a_saved_strategy()
    built = build_step_tree(spec)
    renumbered = renumber_criteria(spec, built.step_id_by_criterion)
    return graph_with([built.root]), {c.id for c in renumbered.criteria}


def test_an_expanded_saved_strategy_counts_as_the_criterion_that_names_it() -> None:
    graph, criteria = _built_over_a_saved_strategy()
    root_id = graph.primary_root_id()
    assert root_id is not None

    shape = stated_shape(graph=graph, root_id=root_id, criteria=criteria, outside=set())

    assert shape.lost == ()
    assert shape.unstated == ()
    assert shape.searches == tuple(sorted(criteria))
    assert shape.holds is True


def test_a_replacement_over_an_expanded_reference_keeps_the_shape() -> None:
    graph, criteria = _built_over_a_saved_strategy()
    interpro = next(
        sid for sid in criteria if graph.steps[sid].search_name == "GenesByInterpro"
    )

    shape = shape_after(
        ReplaceSubtreeOp(
            step_id=interpro, subtree=leaf(interpro, search_name="GenesByInterpro")
        ),
        graph=graph,
        criteria=criteria,
    )

    assert shape.lost == ()
    assert shape.unstated == ()
    assert shape.holds is True


def test_a_replacement_that_drops_the_saved_reference_is_refused() -> None:
    graph, criteria = _built_over_a_saved_strategy()
    root_id = graph.primary_root_id()
    assert root_id is not None
    saved_root = next(
        sid for sid in criteria if graph.steps[sid].kind is StepKind.COMBINE
    )

    shape = shape_after(
        ReplaceSubtreeOp(step_id=root_id, subtree=leaf("only_interpro")),
        graph=graph,
        criteria=criteria,
    )

    assert saved_root in shape.lost
    assert shape.unstated == ("only_interpro",)
    assert shape.holds is False


def test_a_display_name_of_the_sentinel_form_is_not_a_placeholder() -> None:
    """A criterion's text becomes the display name, so only the search counts."""
    named = StrategyStepNode(
        id="a", search_name="GenesByText", display_name="__input_step__"
    )

    assert placeholder_names(combine("c", named, leaf("b"))) == ()


def _spec_of_only_a_saved_strategy() -> OperationalSpec:
    """One criterion, a saved strategy of two searches, with no combine over it."""
    saved = combine(
        "saved_root",
        leaf("saved_a", search_name="GenesByGoTerm"),
        leaf("saved_b", search_name="GenesByText"),
        operator=CombineOp.UNION,
    )
    return OperationalSpec(
        goal="the saved kinases",
        criteria=[
            Criterion(
                id="c1",
                text="the saved kinase strategy",
                saved_strategy_ref=SavedStrategyRef(
                    conversation_id="conv",
                    name="kinases",
                    wdk_strategy_id=999,
                    step_count=3,
                    subtree=saved,
                ),
            ),
        ],
        structure=SpecStructure(root=spec_leaf("c1")),
    )


def _built_over_only_a_saved_strategy() -> tuple[StrategyGraph, set[str]]:
    """The graph that spec builds, and the one criterion id it minted."""
    spec = _spec_of_only_a_saved_strategy()
    built = build_step_tree(spec)
    renumbered = renumber_criteria(spec, built.step_id_by_criterion)
    return graph_with([built.root]), {c.id for c in renumbered.criteria}


def test_a_saved_strategy_no_combine_wraps_counts_as_its_criterion() -> None:
    graph, criteria = _built_over_only_a_saved_strategy()
    root_id = graph.primary_root_id()
    assert root_id is not None

    shape = stated_shape(graph=graph, root_id=root_id, criteria=criteria, outside=set())

    assert criteria == {root_id}
    assert len(graph.steps) == 3
    assert shape.searches == (root_id,)
    assert shape.lost == ()
    assert shape.unstated == ()
    assert shape.holds is True


def test_a_replacement_inside_the_only_saved_strategy_keeps_the_shape() -> None:
    graph, criteria = _built_over_only_a_saved_strategy()
    root_id = graph.primary_root_id()
    assert root_id is not None
    inside = graph.steps[root_id].primary_input_id
    assert inside is not None

    shape = shape_after(
        ReplaceSubtreeOp(
            step_id=inside, subtree=leaf(inside, search_name="GenesByGoTerm")
        ),
        graph=graph,
        criteria=criteria,
    )

    assert shape.lost == ()
    assert shape.unstated == ()
    assert shape.holds is True


def test_a_replacement_that_drops_the_only_saved_strategy_is_refused() -> None:
    graph, criteria = _built_over_only_a_saved_strategy()
    root_id = graph.primary_root_id()
    assert root_id is not None

    shape = shape_after(
        ReplaceSubtreeOp(step_id=root_id, subtree=leaf("step_other")),
        graph=graph,
        criteria=criteria,
    )

    assert shape.lost == (root_id,)
    assert shape.unstated == ("step_other",)
    assert shape.holds is False


def test_an_exported_eda_step_the_spec_states_is_no_departure() -> None:
    """The leaf create_eda_step wires in is a criterion like any other."""
    graph = graph_with(
        [
            combine(
                "root",
                combine("c1", leaf("k1"), leaf("k2")),
                leaf("eda1", search_name="GenesByEdaSubset"),
            )
        ]
    )

    shape = shape_after(
        ReplaceSubtreeOp(
            step_id="k1", subtree=leaf("k1", search_name="GenesByInterpro")
        ),
        graph=graph,
        criteria={"k1", "k2", "eda1"},
    )

    assert shape.searches == ("eda1", "k1", "k2")
    assert shape.lost == ()
    assert shape.unstated == ()
    assert shape.holds is True


def test_a_new_leaf_into_an_occupied_slot_names_the_step_it_overwrites() -> None:
    graph = graph_with([combine("c", leaf("a"), leaf("b"))])

    write = overwritten_slot(
        graph,
        AddLeafOp(
            step=leaf("new"),
            attach=AttachIntoSlot(target_step_id="c", slot="secondary"),
        ),
    )

    assert write == SlotWrite(
        target_step_id="c", slot="secondary", occupant_step_id="b"
    )


def test_a_root_add_and_a_free_slot_overwrite_no_step() -> None:
    graph = graph_with(
        [
            combine("c", leaf("a"), leaf("b")),
            StrategyStepNode(
                id="d",
                search_name=COMBINE_SEARCH_NAME,
                primary_input=leaf("e"),
                operator=CombineOp.INTERSECT,
            ),
        ]
    )
    ops: list[GraphOperation] = [
        AddLeafOp(step=leaf("new"), attach=AttachNewRoot()),
        AddLeafOp(
            step=leaf("new2"),
            attach=AttachIntoSlot(target_step_id="d", slot="secondary"),
        ),
        WireInputOp(target_step_id="d", slot="secondary", source_step_id="a"),
        AddLeafOp(
            step=leaf("new3"),
            attach=AttachIntoSlot(target_step_id="c", slot="primary"),
        ),
    ]

    writes = [overwritten_slot(graph, op) for op in ops]

    assert writes == [
        None,
        None,
        None,
        SlotWrite(target_step_id="c", slot="primary", occupant_step_id="a"),
    ]


def test_only_a_step_off_the_tree_and_undeleted_is_evicted() -> None:
    graph = graph_with(
        [combine("c", combine("n", leaf("a"), leaf("x")), leaf("b")), leaf("gone")]
    )
    kept = SlotWrite(target_step_id="c", slot="primary", occupant_step_id="a")
    off_tree = SlotWrite(target_step_id="c", slot="primary", occupant_step_id="gone")
    deleted = SlotWrite(target_step_id="c", slot="primary", occupant_step_id="removed")

    found = [
        evicted_by(graph, [write], was_reachable={"a", "b", "gone", "removed"})
        for write in (kept, off_tree, deleted)
    ]

    assert found == [None, off_tree, None]
