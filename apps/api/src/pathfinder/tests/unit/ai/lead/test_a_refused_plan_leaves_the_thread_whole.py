"""Structures the planner cannot express, and what the refusal leaves behind.

Every one of them is refused before a single operation reaches the strategy,
and the thread is still the one the dispatch found.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests.unit.ai.lead._disagreement_thread import (
    ROOT,
    STAGE,
    SURFACE,
    DisagreementThread,
    Draft,
    built_spec,
    built_tree,
    joined,
    kept,
    leaf,
    recorded,
    session_holding,
)
from pathfinder.tests.unit.ai.lead._refusal_checks import (
    a_refusal_that_keeps_the_thread_whole,
)

_NOWHERE = "c_nowhere"


async def _entered(monkeypatch: pytest.MonkeyPatch) -> DisagreementThread:
    thread = DisagreementThread(
        monkeypatch,
        spec=built_spec(),
        session=session_holding(built_tree()),
        recorded_build=recorded(SURFACE, STAGE, ROOT),
    )
    await thread.next_turn()
    return thread


def _structured(root: StructureNode | None) -> Draft:
    def _draft(found: OperationalSpec) -> OperationalSpec:
        found.structure = None if root is None else SpecStructure(root=root)
        return found

    return _draft


async def test_a_spec_with_no_structure_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = await _entered(monkeypatch)
    thread.frames(_structured(None), declared=kept(SURFACE, STAGE))

    refusal = await a_refusal_that_keeps_the_thread_whole(thread)

    assert "the edited spec states no structure" in refusal


async def test_a_combine_with_no_operator_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = await _entered(monkeypatch)
    thread.frames(
        _structured(
            StructureNode(
                kind="combine", operator=None, inputs=[leaf(SURFACE), leaf(STAGE)]
            )
        ),
        declared=kept(SURFACE, STAGE),
    )

    refusal = await a_refusal_that_keeps_the_thread_whole(thread)

    assert "a combine states an operator and at least two inputs" in refusal


async def test_a_transform_with_no_input_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = await _entered(monkeypatch)
    thread.frames(
        _structured(
            joined(
                CombineOp.INTERSECT,
                leaf(SURFACE),
                StructureNode(kind="transform", criterion_id=STAGE, inputs=[]),
            )
        ),
        declared=kept(SURFACE, STAGE),
    )

    refusal = await a_refusal_that_keeps_the_thread_whole(thread)

    assert "states no input step" in refusal
    assert f"transform {STAGE!r} states no input step" in refusal


async def test_a_structure_naming_a_criterion_the_spec_lacks_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = await _entered(monkeypatch)
    thread.frames(
        _structured(joined(CombineOp.INTERSECT, leaf(SURFACE), leaf(_NOWHERE))),
        declared=kept(SURFACE, STAGE),
    )

    refusal = await a_refusal_that_keeps_the_thread_whole(thread)

    assert "which the spec lacks" in refusal
    assert f"structure names criterion {_NOWHERE!r}" in refusal


async def test_a_structure_that_leaves_a_live_criterion_out_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The planner never removes a step the edit did not ask it to remove."""
    thread = await _entered(monkeypatch)
    thread.frames(_structured(leaf(SURFACE)), declared=kept(SURFACE, STAGE))

    refusal = await a_refusal_that_keeps_the_thread_whole(thread)

    assert "the planned strategy holds" in refusal
    assert f"the edited spec states ['{SURFACE}', '{STAGE}']" in refusal
