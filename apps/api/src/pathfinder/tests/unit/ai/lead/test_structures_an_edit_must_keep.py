"""Structures whose shape an edit has to preserve: options, subtrees, transforms.

Each one addresses more than one step, or no step of its own, so the planner
has to read the strategy rather than the structure alone.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StrategyStepNode,
)

from pathfinder.ai.lead.deltas import EditDelta
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.operations.resolutions import compute_delete_choices
from pathfinder.tests.unit.ai.lead._disagreement_drafts import (
    NESTED_ROOT,
    PROTEOME,
    THIRD,
    canvas_deletes,
    nested_spec,
    nested_tree,
    with_the_percentile,
    with_the_proteome,
)
from pathfinder.tests.unit.ai.lead._disagreement_facts import (
    OpFacts,
    committed_facts,
    facts_of,
    spec_facts,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    STAGE_PERCENTILE,
    STAGE_TIMEPOINT,
    SURFACE,
    DisagreementThread,
    Draft,
    built_spec,
    built_tree,
    declared,
    joined,
    kept,
    leaf,
    recorded,
    session_holding,
)

_OPTION = "c_stage_dataset"
_SAVED = "step_5a6b7c8d"
_SAVED_A = "step_6b7c8d9e"
_SAVED_B = "step_7c8d9e0f"
_WITH_SAVED = "step_8d9e0f1a"
_ORTH = "step_9e0f1a2b"
_ORTH_PARAM = "ortholog_organism"


def _new_root(thread: DisagreementThread) -> str:
    root = thread.graph.primary_root_id()
    assert root is not None
    return root


def _with_the_option(value: str | None) -> Draft:
    """An option criterion the structure leaves out, open or answered."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria = [c for c in found.criteria if c.id != _OPTION]
        found.criteria.append(
            Criterion(
                id=_OPTION,
                text="read the 2019 dataset",
                search_name="GenesByRNASeqEvidence",
                resolved_params={}
                if value is None
                else {"dataset": StringValue(value=value)},
                open_params=[]
                if value is not None
                else [OpenSlot(criterion_id=_OPTION, param_name="dataset")],
            )
        )
        return found

    return _draft


def _without_the_option() -> Draft:
    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria = [c for c in found.criteria if c.id != _OPTION]
        return found

    return _draft


async def test_an_option_whose_carrier_the_canvas_deleted_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No live step runs the option's search, so nothing can carry its value."""
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    await thread.next_turn()
    thread.frames(_with_the_option(None), declared=[], disposition="needs_user")
    await thread.edit()
    canvas_deletes(thread.graph, STAGE)
    await thread.next_turn()
    thread.frames(_with_the_option("ds2019"), declared=kept(SURFACE))

    refusal = await thread.edit()

    assert isinstance(refusal, str)
    assert _OPTION in refusal
    assert thread.committed == []
    assert sorted(thread.graph.steps) == [SURFACE]


async def test_dropping_that_option_is_the_way_out_and_costs_no_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The option never owned a step, so letting it go changes no step."""
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    await thread.next_turn()
    thread.frames(_with_the_option(None), declared=[], disposition="needs_user")
    await thread.edit()
    canvas_deletes(thread.graph, STAGE)
    await thread.next_turn()
    thread.frames(_without_the_option(), declared=declared("dropped", _OPTION))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.committed == []
    assert (
        delta.description == "The strategy already states everything the edit asks for."
    )
    assert thread.criteria == [SURFACE]


def _saved_subtree() -> StrategyStepNode:
    """An inserted saved strategy: one criterion, two steps under its root."""
    return StrategyStepNode(
        id=_SAVED,
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.UNION,
        primary_input=StrategyStepNode(id=_SAVED_A, search_name="GenesByGoTerm"),
        secondary_input=StrategyStepNode(id=_SAVED_B, search_name="GenesByText"),
    )


def _thread_with_a_saved_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> DisagreementThread:
    tree = StrategyStepNode(
        id=_WITH_SAVED,
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.INTERSECT,
        primary_input=built_tree(),
        secondary_input=_saved_subtree(),
    )
    spec = built_spec()
    assert spec.structure is not None
    spec.criteria.append(Criterion(id=_SAVED, text="my saved marker panel"))
    spec.structure = SpecStructure(
        root=joined(CombineOp.INTERSECT, spec.structure.root, leaf(_SAVED))
    )
    return DisagreementThread(
        monkeypatch,
        spec=spec,
        session=session_holding(tree),
        recorded_build=recorded(SURFACE, STAGE, ROOT, _SAVED, _SAVED_A, _SAVED_B),
    )


def _dropping_the_saved() -> Draft:
    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.criteria = [c for c in found.criteria if c.id != _SAVED]
        found.structure = built_spec().structure
        return found

    return _draft


async def test_a_saved_strategy_criterion_takes_its_whole_subtree_when_it_is_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One criterion addresses the subtree root, and the drop accounts for all of it."""
    thread = _thread_with_a_saved_strategy(monkeypatch)
    await thread.next_turn()
    thread.frames(
        _dropping_the_saved(),
        declared=[*kept(SURFACE, STAGE), *declared("dropped", _SAVED)],
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [(op.kind, op.step_id) for op in committed_facts(thread.committed)] == [
        ("deleteStep", _SAVED)
    ]
    assert sorted(thread.graph.steps) == sorted([SURFACE, STAGE, ROOT])
    assert thread.criteria == [SURFACE, STAGE]
    assert sorted(delta.dropped_step_ids) == sorted(
        [_SAVED, _SAVED_A, _SAVED_B, _WITH_SAVED]
    )


async def test_a_saved_strategy_criterion_is_untouched_while_a_sibling_is_edited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The subtree keeps every id and every value the edit did not name."""
    thread = _thread_with_a_saved_strategy(monkeypatch)
    await thread.next_turn()
    untouched = facts_of(thread.facts(), _SAVED, _SAVED_A, _SAVED_B, _WITH_SAVED)
    thread.frames(
        with_the_percentile(90),
        declared=[*kept(SURFACE, _SAVED), *declared("changed", STAGE)],
    )

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed) == [
        OpFacts(
            kind="updateStepParams",
            step_id=STAGE,
            parameters={STAGE_PERCENTILE: "90"},
        )
    ]
    assert (
        facts_of(thread.facts(), _SAVED, _SAVED_A, _SAVED_B, _WITH_SAVED) == untouched
    )
    assert sorted(delta.preserved_step_ids) == sorted([SURFACE, _SAVED])


def _transform_thread(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    """``orthologs(surface INTERSECT stage)``, the transform stated as a criterion."""
    tree = StrategyStepNode(
        id=_ORTH,
        search_name="GenesByOrthologs",
        display_name="P. vivax orthologs",
        parameters={_ORTH_PARAM: MultiPickValue(values=["P. vivax P01"])},
        primary_input=built_tree(),
    )
    spec = built_spec()
    assert spec.structure is not None
    spec.criteria.append(
        Criterion(
            id=_ORTH,
            text="P. vivax orthologs",
            search_name="GenesByOrthologs",
            role="transform",
            resolved_params={_ORTH_PARAM: MultiPickValue(values=["P. vivax P01"])},
        )
    )
    spec.structure = SpecStructure(
        root=_transform_over(spec.structure.root),
    )
    return DisagreementThread(
        monkeypatch,
        spec=spec,
        session=session_holding(tree),
        recorded_build=recorded(SURFACE, STAGE, ROOT, _ORTH),
    )


def _transform_over(inner: StructureNode) -> StructureNode:
    return StructureNode(kind="transform", criterion_id=_ORTH, inputs=[inner])


async def test_a_transforms_own_parameter_moves_without_touching_its_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = _transform_thread(monkeypatch)
    await thread.next_turn()
    untouched = facts_of(thread.facts(), SURFACE, STAGE, ROOT)

    def _draft(found: OperationalSpec) -> OperationalSpec:
        for criterion in found.criteria:
            if criterion.id == _ORTH:
                criterion.resolved_params = {
                    _ORTH_PARAM: MultiPickValue(values=["P. berghei ANKA"])
                }
        return found

    thread.frames(_draft, declared=[*kept(SURFACE, STAGE), *declared("changed", _ORTH)])

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert committed_facts(thread.committed) == [
        OpFacts(
            kind="updateStepParams",
            step_id=_ORTH,
            parameters={_ORTH_PARAM: '["P. berghei ANKA"]'},
        )
    ]
    assert facts_of(thread.facts(), SURFACE, STAGE, ROOT) == untouched


async def test_a_criterion_added_under_a_transform_is_wired_into_its_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The new combine goes under the transform, which keeps reading one input."""
    thread = _transform_thread(monkeypatch)
    await thread.next_turn()

    def _draft(found: OperationalSpec) -> OperationalSpec:
        found = with_the_proteome(2)(found)
        assert found.structure is not None
        inner = found.structure.root.inputs[0]
        found.structure = SpecStructure(
            root=_transform_over(
                joined(CombineOp.INTERSECT, inner.inputs[0], leaf(PROTEOME))
            )
        )
        return found

    thread.frames(_draft, declared=kept(SURFACE, STAGE, _ORTH))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [op.kind for op in committed_facts(thread.committed)] == [
        "addLeaf",
        "addCombine",
        "wireInput",
    ]
    assert thread.graph.primary_root_id() == _ORTH
    assert thread.graph.steps[_ORTH].primary_input_id != ROOT


async def test_deleting_a_transforms_input_on_the_canvas_takes_the_whole_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The canvas offers one resolution for it, and it removes the transform too."""
    thread = _transform_thread(monkeypatch)
    choices = compute_delete_choices(thread.graph, ROOT)

    dropped = canvas_deletes(thread.graph, ROOT)
    await thread.next_turn()

    assert [(c.resolution.value, c.is_default) for c in choices] == [
        ("delete-subtree", True)
    ]
    assert dropped == sorted([SURFACE, STAGE, ROOT, _ORTH])
    assert thread.graph.steps == {}
    assert thread.criteria == []
    assert thread.spec.structure is None


def _flat_restatement(extra: bool) -> Draft:
    """The same three criteria as one flat combine, with or without a fourth."""

    def _draft(found: OperationalSpec) -> OperationalSpec:
        sides = [leaf(SURFACE), leaf(STAGE), leaf(THIRD)]
        if extra:
            found = with_the_proteome(2)(found)
            sides.append(leaf(PROTEOME))
        found.structure = SpecStructure(root=joined(CombineOp.INTERSECT, *sides))
        return found

    return _draft


async def test_a_flat_restatement_of_the_same_tree_asks_for_no_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An n-ary combine over the same ordered pairs is the tree the strategy holds."""
    thread = DisagreementThread(
        monkeypatch,
        spec=nested_spec(),
        session=session_holding(nested_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT, THIRD, NESTED_ROOT),
    )
    await thread.next_turn()
    untouched = thread.facts()
    thread.frames(_flat_restatement(extra=False), declared=kept(SURFACE, STAGE, THIRD))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert thread.committed == []
    assert thread.facts() == untouched
    assert (
        delta.description == "The strategy already states everything the edit asks for."
    )
    assert sorted(delta.preserved_step_ids) == sorted([SURFACE, STAGE, THIRD])


async def test_a_flat_restatement_with_a_fourth_criterion_adds_only_that_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = DisagreementThread(
        monkeypatch,
        spec=nested_spec(),
        session=session_holding(nested_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT, THIRD, NESTED_ROOT),
    )
    await thread.next_turn()
    untouched = facts_of(thread.facts(), SURFACE, STAGE, THIRD, ROOT, NESTED_ROOT)
    thread.frames(_flat_restatement(extra=True), declared=kept(SURFACE, STAGE, THIRD))

    delta = await thread.edit()

    assert isinstance(delta, EditDelta)
    assert [(op.kind, op.step_id) for op in committed_facts(thread.committed)] == [
        ("addLeaf", PROTEOME),
        ("addCombine", _new_root(thread)),
    ]
    assert facts_of(thread.facts(), SURFACE, STAGE, THIRD, ROOT, NESTED_ROOT) == (
        untouched
    )
    assert spec_facts(thread.spec)[STAGE] == {
        STAGE_PERCENTILE: "80",
        STAGE_TIMEPOINT: "40",
    }
    assert delta.added_step_ids == [PROTEOME]
