"""``set_structure`` refuses a tree that leaves the combine the message names
by its place, or moves another combine, and takes the tree that flips it. An
edit that names no place changes a combine's operator only to one it states."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone.frame_structure import set_structure
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.named_combine import NamedCombine, stated_operators
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_EXPRESSION = "step_c341eba4"
_SIGNAL = "step_46ae849e"
_TM = "step_dff6f41b"


def _tree(outer: CombineOp, inner: CombineOp) -> StructureNode:
    return StructureNode(
        kind="combine",
        operator=outer,
        inputs=[
            StructureNode(kind="leaf", criterion_id=_EXPRESSION),
            StructureNode(
                kind="combine",
                operator=inner,
                inputs=[
                    StructureNode(kind="leaf", criterion_id=_SIGNAL),
                    StructureNode(kind="leaf", criterion_id=_TM),
                ],
            ),
        ],
    )


def _state() -> AgentToolState:
    state = AgentToolState()
    for criterion_id, text, search in (
        (_EXPRESSION, "genes expressed in blood stages", "GenesByRNASeqPercentile"),
        (_SIGNAL, "proteins with a predicted signal peptide", "GenesWithSignalPeptide"),
        (_TM, "proteins with a transmembrane domain", "GenesByTransmembraneDomains"),
    ):
        state.frame_set_criterion(
            Criterion(id=criterion_id, text=text, search_name=search)
        )
    state.named_combine = NamedCombine(position="root", operator=CombineOp.UNION)
    state.held_structure = SpecStructure(
        root=_tree(CombineOp.INTERSECT, CombineOp.INTERSECT)
    )
    return state


@pytest.mark.asyncio
async def test_a_tree_that_flips_the_inner_combine_is_refused() -> None:
    state = _state()

    with pytest.raises(ModelRetry) as refused:
        await set_structure(
            agent_run_context(agent_state=state),
            root=_tree(CombineOp.INTERSECT, CombineOp.UNION),
        )

    assert refused.value.message.startswith(
        "The structure is refused: the user names the root combine, which must "
        "be UNION, but the tree joins it at INTERSECT."
    )
    assert state.operational_spec_draft.structure is None


@pytest.mark.asyncio
async def test_a_tree_that_flips_the_root_alone_is_set() -> None:
    state = _state()
    flipped = _tree(CombineOp.UNION, CombineOp.INTERSECT)

    await set_structure(agent_run_context(agent_state=state), root=flipped)

    assert state.operational_spec_draft.structure == SpecStructure(root=flipped)


_UNDO = "Undo that, keep the intersection."
_KEPT_INTERSECTION = Constraint(
    kind=ConstraintKind.COMBINATION,
    label="combination",
    requested_value="surface features AND blood-stage expression",
    source=ConstraintSource.USER_EXPLICIT,
)


def _unplaced_state(message: str, *, held: bool = True) -> AgentToolState:
    state = _state()
    state.named_combine = NamedCombine.read(message)
    state.stated_operators = stated_operators(message)
    state.combination_requirements = [_KEPT_INTERSECTION]
    state.held_structure = (
        SpecStructure(root=_tree(CombineOp.INTERSECT, CombineOp.INTERSECT))
        if held
        else None
    )
    return state


def _inner_union_first() -> StructureNode:
    """``INTERSECT(UNION(signal peptide, TM), expression)``."""
    return StructureNode(
        kind="combine",
        operator=CombineOp.INTERSECT,
        inputs=[
            StructureNode(
                kind="combine",
                operator=CombineOp.UNION,
                inputs=[
                    StructureNode(kind="leaf", criterion_id=_SIGNAL),
                    StructureNode(kind="leaf", criterion_id=_TM),
                ],
            ),
            StructureNode(kind="leaf", criterion_id=_EXPRESSION),
        ],
    )


@pytest.mark.asyncio
async def test_an_edit_that_moves_a_combine_to_an_unstated_operator_is_refused() -> (
    None
):
    state = _unplaced_state(_UNDO)

    with pytest.raises(ModelRetry) as refused:
        await set_structure(
            agent_run_context(agent_state=state), root=_inner_union_first()
        )

    assert refused.value.message == (
        f"The structure is refused: the tree moves the combine over {_SIGNAL}, "
        f"{_TM} from INTERSECT to UNION, and the message states no UNION. A "
        f"combine's operator changes only to one the message states."
    )
    assert state.operational_spec_draft.structure is None


@pytest.mark.asyncio
async def test_an_edit_that_states_the_new_operator_moves_the_combine() -> None:
    state = _unplaced_state("make the inner one a union")
    state.combination_requirements = []

    await set_structure(agent_run_context(agent_state=state), root=_inner_union_first())

    assert state.operational_spec_draft.structure == SpecStructure(
        root=_inner_union_first()
    )


@pytest.mark.asyncio
async def test_an_edit_that_changes_no_operator_is_set() -> None:
    state = _unplaced_state(_UNDO)
    kept = _tree(CombineOp.INTERSECT, CombineOp.INTERSECT)

    await set_structure(agent_run_context(agent_state=state), root=kept)

    assert state.operational_spec_draft.structure == SpecStructure(root=kept)


@pytest.mark.asyncio
async def test_a_new_build_with_no_held_tree_is_not_checked_for_moves() -> None:
    state = _unplaced_state(_UNDO, held=False)

    await set_structure(agent_run_context(agent_state=state), root=_inner_union_first())

    assert state.operational_spec_draft.structure == SpecStructure(
        root=_inner_union_first()
    )


@pytest.mark.parametrize(
    ("message", "stated"),
    [
        (_UNDO, {CombineOp.INTERSECT}),
        ("make the inner one a union", {CombineOp.UNION}),
        ("subtract them: expression minus TM", {CombineOp.MINUS}),
        (
            "union these, then intersects with that",
            {CombineOp.UNION, CombineOp.INTERSECT},
        ),
        ("restore the previous tree", set()),
    ],
)
def test_the_operator_words_of_a_message_state_its_operators(
    message: str, stated: set[CombineOp]
) -> None:
    assert stated_operators(message) == frozenset(stated)
