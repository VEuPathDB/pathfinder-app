"""A card answer that names a stand-in retires exactly the requirements its
question names by number, replaced by the stand-in."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import uuid4

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from pydantic_ai import ModelRetry

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.lead_consult import (
    apply_option_bindings,
    card_stand_ins,
    consult_can_ask,
    consult_user,
)
from pathfinder.domain.strategy.constraints import ConstraintKind, ReplacedLifecycle
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_REQUEST = (
    "Cytauxzoon felis Winnie genes with a predicted GPI anchor or a signal peptide."
)
_REPLACE = (
    "What alternative evidence type should replace the unavailable predicted "
    "GPI-anchor branch?"
)
_STAND_IN = (
    "Use a text search for GPI anchor in the gene product descriptions as the stand-in"
)
_ORGANISM = requirement(ConstraintKind.ORGANISM, "organism", "Cytauxzoon felis Winnie")
_GPI = requirement(ConstraintKind.OTHER, "predicted GPI anchor", "predicted GPI anchor")
_SIGNAL = requirement(ConstraintKind.OTHER, "signal peptide", "signal peptide")
_COMBINATION = requirement(
    ConstraintKind.COMBINATION,
    "evidence combination",
    "predicted GPI anchor OR signal peptide",
)
_HELD = [_ORGANISM, _GPI, _SIGNAL, _COMBINATION]


def _held(state: PipelineState, value: str) -> str:
    [held] = [c.id for c in state.domain.requirements if c.requested_value == value]
    return held


def _answered(
    prompt: str, note: str, replaced: Mapping[str, Sequence[str]]
) -> PipelineState:
    state = pipeline_state(
        "piroplasmadb",
        user_prompt=_REQUEST,
        user_message_id=uuid4(),
        domain=StrategyDomainState(requirements=list(_HELD)),
    )
    card = CardQuestion(id="q1", prompt=prompt, dimension=ConstraintKind.OTHER)
    answer = UserQuestionAnswer(question_id="q1", prompt=prompt, note=note)

    apply_option_bindings(state, [answer], [card], sheets={}, replaced=replaced)

    return state


def test_the_requirement_the_question_names_is_replaced_by_the_stand_in() -> None:
    state = _answered(_REPLACE, _STAND_IN, {_REPLACE: [_GPI.id]})

    retired = {r.constraint.id: r.lifecycle for r in state.domain.retired_requirements}
    assert retired == {_GPI.id: ReplacedLifecycle(by=_held(state, _STAND_IN))}
    assert [c.requested_value for c in state.domain.requirements] == [
        "Cytauxzoon felis Winnie",
        "signal peptide",
        "predicted GPI anchor OR signal peptide",
        _STAND_IN,
    ]


def test_a_question_that_names_no_requirement_retires_nothing() -> None:
    """The prompt asks to replace the GPI anchor, and names no number."""
    state = _answered(_REPLACE, _STAND_IN, {})

    assert state.domain.retired_requirements == []


def test_a_question_that_names_two_requirements_replaces_both() -> None:
    state = _answered(_REPLACE, _STAND_IN, {_REPLACE: [_GPI.id, _COMBINATION.id]})

    retired = {r.constraint.id: r.lifecycle for r in state.domain.retired_requirements}
    stand_in = ReplacedLifecycle(by=_held(state, _STAND_IN))
    assert retired == {_GPI.id: stand_in, _COMBINATION.id: stand_in}
    assert _SIGNAL in state.domain.requirements


def _card(*numbers: str) -> CardQuestion:
    return CardQuestion(
        id="q1", prompt=_REPLACE, dimension=ConstraintKind.OTHER, replaces=list(numbers)
    )


def test_the_card_maps_each_number_to_the_held_id() -> None:
    assert card_stand_ins([_card("R2", "R4")], _HELD) == {
        _REPLACE: [_GPI.id, _COMBINATION.id]
    }


def test_a_number_the_list_lacks_is_sent_back_with_the_numbers_it_holds() -> None:
    with pytest.raises(ModelRetry, match=r"\['R5'\].*R1, R2, R3, R4"):
        card_stand_ins([_card("R5")], _HELD)


def test_no_stand_in_replaces_the_organism() -> None:
    with pytest.raises(ModelRetry, match=r"\['R1'\]"):
        card_stand_ins([_card("R1")], _HELD)


async def test_the_numbers_the_card_showed_decide_after_the_list_moves() -> None:
    """A requirement the answer's turn adds ahead of R2 moves no replacement."""
    state = pipeline_state(
        "piroplasmadb",
        user_prompt=_REQUEST,
        user_message_id=uuid4(),
        domain=StrategyDomainState(requirements=list(_HELD)),
    )
    deps = lead_deps(state)
    card = _card("R2")
    await consult_can_ask(
        run_context_for(deps, "call_card"), [card], reply="One question."
    )
    secreted = requirement(ConstraintKind.OTHER, "secreted", "secreted")
    state.domain.requirements = [secreted, *_HELD]
    state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(question_id="q1", prompt=_REPLACE, note=_STAND_IN)
        ]
    }

    await consult_user(
        run_context_for(deps, "call_card"), questions=[card], reply="One question."
    )

    assert [r.constraint.id for r in state.domain.retired_requirements] == [_GPI.id]
