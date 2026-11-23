from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import UserQuestionAnswer
from veupathdb.domain.parameters import MultiPickValue, ParamValue

from strategist.ai.agents.frame_option_checks import hold_an_option_to_its_parameter
from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.lead_consult import apply_option_bindings
from strategist.domain.strategy.card_answers import option_refusal, spec_bound_by_card
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from strategist.domain.strategy.organism_picks import (
    OrganismPick,
    organism_questions,
)
from strategist.domain.strategy.question_options import SetValues
from strategist.domain.strategy.questions import SlotQuestion
from strategist.tests.unit.ai.lead.conftest import pipeline_state
from strategist.tests.unit.ai.tools.conftest import agent_run_context

_SPECIES = "Candida auris"
_BRACKETED = "[Candida] auris"
_STRAIN = "[Candida] auris B8441"
_OTHER = "Candida albicans SC5314"


def _criterion(*organisms: str) -> Criterion:
    return Criterion(
        id="c_one",
        text="secreted proteins",
        search_name="GenesWithSignalPeptide",
        organism_param="organism",
        resolved_params={
            "organism": BoundValue(
                value=MultiPickValue(values=list(organisms)), source="stated"
            )
        },
    )


def _organism_bound(value: str | list[str]) -> ParamValue:
    spec = OperationalSpec(criteria=[_criterion(_OTHER)])
    binding = SetValues(criterion_id="c_one", params={"organism": value})

    bound = spec_bound_by_card(spec, binding, option_id="o", sheets={}, expressions={})

    assert option_refusal(spec, binding, sheets={}, expressions={}) is None
    return bound.criteria[0].param_values["organism"]


def test_a_bracketed_term_on_a_card_is_one_organism() -> None:
    assert _organism_bound(_BRACKETED) == MultiPickValue(values=[_BRACKETED])


def test_a_list_on_a_card_is_each_of_its_organisms() -> None:
    assert _organism_bound([_BRACKETED, _OTHER]) == MultiPickValue(
        values=[_BRACKETED, _OTHER]
    )


def test_a_list_written_as_text_arrives_as_text() -> None:
    binding = SetValues.model_validate(
        {"criterionId": "c_one", "params": {"organism": f'["{_BRACKETED}"]'}}
    )

    assert binding.params == {"organism": f'["{_BRACKETED}"]'}


async def test_frame_offers_a_bracketed_organism() -> None:
    ctx = agent_run_context()
    ctx.deps.agent_state.operational_spec_draft = OperationalSpec(
        criteria=[_criterion(_OTHER)]
    )
    question = SlotQuestion(
        question="Which organism do you mean?",
        dimension=ConstraintKind.ORGANISM,
        recommended_value=_BRACKETED,
        criterion_id="c_one",
        param_name="organism",
        options=[_BRACKETED, _OTHER],
    )

    held = await hold_an_option_to_its_parameter(
        ctx, FrameResult(disposition="needs_user", open_questions=[question])
    )

    assert held == []


def test_a_consulted_bracketed_strain_reaches_the_criterion() -> None:
    requirement = Constraint(
        kind=ConstraintKind.ORGANISM,
        requested_value=_SPECIES,
        label="organism",
        source=ConstraintSource.USER_EXPLICIT,
        quote=_SPECIES,
    )
    [question] = organism_questions(
        [requirement], [OrganismPick(quote=_SPECIES, offered=[_STRAIN, _OTHER])]
    )
    state = pipeline_state(
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            open_questions=[question],
            operational_spec=OperationalSpec(criteria=[_criterion(_SPECIES)]),
        ),
    )
    state.domain.requirements = [requirement]

    apply_option_bindings(
        state,
        [
            UserQuestionAnswer(
                question_id="q1", prompt=question.question, chosen_labels=[_STRAIN]
            )
        ],
        sheets={},
    )

    spec = state.domain.operational_spec
    assert spec is not None
    assert spec.criteria[0].param_values["organism"] == MultiPickValue(values=[_STRAIN])
