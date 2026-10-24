"""FRAME is sent back when a ready spec's structure names a criterion the draft
never bound, so the pass binds it or drops it before the build refuses it."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext

from pathfinder.ai.agents.frame_result_checks import (
    hold_the_structure_to_bound_criteria,
)
from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.structure_bindings import unbound_in_structure
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context


def _spec(*, bound_lanterns: bool) -> OperationalSpec:
    return OperationalSpec(
        goal="lantern genes with a reef domain",
        criteria=[
            Criterion(id="c_reef", text="reef domain", search_name="GenesByReef"),
            Criterion(
                id="c_lantern",
                text="lantern expression",
                search_name="GenesByLantern" if bound_lanterns else "",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode.model_validate(
                {
                    "kind": "combine",
                    "operator": "INTERSECT",
                    "inputs": [
                        {"kind": "leaf", "criterionId": "c_reef"},
                        {"kind": "leaf", "criterionId": "c_lantern"},
                        {"kind": "leaf", "criterionId": "c_tide"},
                    ],
                }
            )
        ),
    )


def _context(spec: OperationalSpec, refusals: int = 0) -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    ctx.deps.agent_state.operational_spec_draft = spec
    ctx.deps.agent_state.refusals = refusals
    return ctx


def test_the_criteria_a_structure_names_and_the_draft_never_bound() -> None:
    assert unbound_in_structure(_spec(bound_lanterns=False)) == [
        "c_lantern",
        "c_tide",
    ]
    assert unbound_in_structure(_spec(bound_lanterns=True)) == ["c_tide"]


def test_a_ready_spec_naming_an_unbound_criterion_is_sent_back() -> None:
    ctx = _context(_spec(bound_lanterns=False))

    with pytest.raises(ModelRetry) as sent_back:
        hold_the_structure_to_bound_criteria(ctx, FrameResult())

    assert str(sent_back.value) == (
        "set_structure names c_lantern, c_tide, and the draft binds no search for "
        "them. Bind each with set_criterion, or call set_structure again without "
        "them: the build refuses a node no bound criterion stands for."
    )
    assert ctx.deps.agent_state.refusals == 1


def test_a_spec_that_waits_on_the_user_is_not_held() -> None:
    result = FrameResult(disposition="needs_user")

    held = hold_the_structure_to_bound_criteria(
        _context(_spec(bound_lanterns=False)), result
    )

    assert held == result


def test_a_structure_of_bound_criteria_passes() -> None:
    spec = _spec(bound_lanterns=True)
    assert spec.structure is not None
    spec.structure.root.inputs.pop()

    assert hold_the_structure_to_bound_criteria(_context(spec), FrameResult()) == (
        FrameResult()
    )


def test_at_the_bound_the_unbound_criteria_are_a_named_gap() -> None:
    held = hold_the_structure_to_bound_criteria(
        _context(_spec(bound_lanterns=True), refusals=REFUSALS_PER_CHECK),
        FrameResult(),
    )

    assert isinstance(held, FrameResult)
    assert held.gaps == [
        PassGap(
            kind="structure_names_unbound",
            sentence="The structure names c_tide, which no bound criterion stands for.",
        )
    ]
