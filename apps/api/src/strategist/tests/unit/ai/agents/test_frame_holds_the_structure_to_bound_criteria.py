"""FRAME is sent back when a ready spec's structure names a criterion the draft
never bound, so the pass binds it or drops it before the build refuses it."""

from __future__ import annotations

from pydantic_ai.tools import RunContext

from strategist.ai.agents.frame_result_checks import (
    hold_the_structure_to_bound_criteria,
)
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.lead.deltas import FrameResult, PassGap
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.structure_bindings import unbound_in_structure
from strategist.tests._support.held_answers import let_through, said
from strategist.tests.unit.ai.tools.conftest import agent_run_context


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


def _context(spec: OperationalSpec) -> RunContext[AgentDeps]:
    ctx = agent_run_context()
    ctx.deps.agent_state.operational_spec_draft = spec
    return ctx


def test_the_criteria_a_structure_names_and_the_draft_never_bound() -> None:
    assert unbound_in_structure(_spec(bound_lanterns=False)) == [
        "c_lantern",
        "c_tide",
    ]
    assert unbound_in_structure(_spec(bound_lanterns=True)) == ["c_tide"]


def test_a_ready_spec_naming_an_unbound_criterion_is_sent_back() -> None:
    held = hold_the_structure_to_bound_criteria(
        _context(_spec(bound_lanterns=False)), FrameResult()
    )

    assert said(held) == [
        f"set_structure names {node}, and the draft binds no search for it. Bind "
        "it with set_criterion, or call set_structure again without it: the build "
        "refuses a node no bound criterion stands for."
        for node in ("c_lantern", "c_tide")
    ]
    assert [answer.problem.key.criterion for answer in held] == ["c_lantern", "c_tide"]


def test_a_spec_that_waits_on_the_user_is_not_held() -> None:
    result = FrameResult(disposition="needs_user")

    held = hold_the_structure_to_bound_criteria(
        _context(_spec(bound_lanterns=False)), result
    )

    assert held == []


def test_a_structure_of_bound_criteria_passes() -> None:
    spec = _spec(bound_lanterns=True)
    assert spec.structure is not None
    spec.structure.root.inputs.pop()

    assert hold_the_structure_to_bound_criteria(_context(spec), FrameResult()) == []


def test_at_the_bound_the_unbound_criteria_are_a_named_gap() -> None:
    held = hold_the_structure_to_bound_criteria(
        _context(_spec(bound_lanterns=True)), FrameResult()
    )

    assert let_through(held, FrameResult()).gaps == [
        PassGap(
            kind="structure_names_unbound",
            sentence="The structure names c_tide, which no bound criterion stands for.",
        )
    ]


def test_a_criterion_waiting_for_its_analysis_counts_as_bound() -> None:
    spec = _spec(bound_lanterns=True)
    spec.criteria.append(
        Criterion(id="c_tide", text="tide samples", needs_analysis_on="DS_tide")
    )

    assert unbound_in_structure(spec) == []
