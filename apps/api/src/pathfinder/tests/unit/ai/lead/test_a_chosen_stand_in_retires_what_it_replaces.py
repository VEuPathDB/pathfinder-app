"""A card answer that names a stand-in for a requirement the question asks to
replace retires that requirement, replaced by the stand-in."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import UserQuestionAnswer

from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.lead_consult import apply_option_bindings
from pathfinder.domain.strategy.constraints import ConstraintKind, ReplacedLifecycle
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state, requirement

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


def _answered(prompt: str, note: str) -> PipelineState:
    state = pipeline_state(
        "piroplasmadb",
        user_prompt=_REQUEST,
        user_message_id=uuid4(),
        domain=StrategyDomainState(requirements=[_ORGANISM, _GPI, _SIGNAL]),
    )
    card = CardQuestion(id="q1", prompt=prompt, dimension=ConstraintKind.OTHER)
    answer = UserQuestionAnswer(question_id="q1", prompt=prompt, note=note)

    apply_option_bindings(state, [answer], [card], sheets={})

    return state


def test_the_requirement_the_question_replaces_is_replaced_by_the_stand_in() -> None:
    state = _answered(_REPLACE, _STAND_IN)

    retired = {r.constraint.key: r.lifecycle for r in state.domain.retired_requirements}
    assert retired == {_GPI.key: ReplacedLifecycle(by=f"other:{_STAND_IN}")}
    assert [c.requested_value for c in state.domain.requirements] == [
        "Cytauxzoon felis Winnie",
        "signal peptide",
        _STAND_IN,
    ]


def test_a_question_that_asks_for_no_replacement_retires_nothing() -> None:
    state = _answered(
        "Which predicted GPI anchor evidence should the search read?", _STAND_IN
    )

    assert state.domain.retired_requirements == []


def test_a_stand_in_that_states_how_it_combines_replaces_both() -> None:
    note = f"{_STAND_IN} and keep it OR with the signal peptide"
    state = pipeline_state(
        "piroplasmadb",
        user_prompt=_REQUEST,
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            requirements=[_ORGANISM, _GPI, _SIGNAL, _COMBINATION]
        ),
    )
    card = CardQuestion(id="q1", prompt=_REPLACE, dimension=ConstraintKind.OTHER)
    answer = UserQuestionAnswer(question_id="q1", prompt=_REPLACE, note=note)

    apply_option_bindings(state, [answer], [card], sheets={})

    retired = {r.constraint.key: r.lifecycle for r in state.domain.retired_requirements}
    stand_in = ReplacedLifecycle(by=f"combination:{note}")
    assert retired == {_GPI.key: stand_in, _COMBINATION.key: stand_in}
    assert _SIGNAL in state.domain.requirements
