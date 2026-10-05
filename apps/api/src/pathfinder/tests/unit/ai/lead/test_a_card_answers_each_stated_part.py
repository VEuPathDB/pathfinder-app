"""A proposal card answers each requirement this message states, by its key,
with a change or a question; a requirement the strategy holds needs neither."""

from __future__ import annotations

import pytest
from assistant_core.graph.turn_state import PendingApproval, UserQuestionAnswer
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.card_reply import CARD_NOT_SHOWN
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.lead_agent import build_lead_toolset
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.lead_proposal import refuse_a_card_that_leaves_a_part
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.proposal import (
    AddCriterionChange,
    CardProposal,
    ProposedChange,
    SetValuesChange,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
    user_intent,
)
from pathfinder.tests.unit.ai.tools.conftest import unwrap_function_toolset

pytestmark = pytest.mark.usefixtures("recorded_site_organisms")

_ORGANISM = "Trypanosoma congolense IL3000"
_MESSAGE = f"Find the GPI-anchored surface proteins of {_ORGANISM}"
_ANSWER = (
    'use the phrase "GPI anchored", and also include the variant surface '
    "glycoprotein products"
)
_PHRASE = requirement(ConstraintKind.OTHER, "Phrase", "GPI anchored")
_VSG = requirement(ConstraintKind.OTHER, "VSG products", "variant surface glycoprotein")
_THE_ORGANISM = requirement(ConstraintKind.ORGANISM, "Organism", _ORGANISM)
_PHRASE_KEY = "other:GPI anchored"
_VSG_KEY = "other:variant surface glycoprotein"


def _text_step(expression: str, organism: str) -> Criterion:
    return Criterion(
        id="step_text",
        text="surface proteins",
        search_name="GenesByText",
        organism_param="text_search_organism",
        resolved_params={
            "text_expression": BoundValue(
                value=StringValue(value=expression), source="stated"
            ),
            "text_search_organism": BoundValue(
                value=MultiPickValue(values=[organism]), source="stated"
            ),
        },
    )


async def _answered(
    *stated: Constraint, expression: str = "surface", organism: str = _ORGANISM
) -> LeadDeps:
    """The thread once the researcher answered the term question on a card."""
    step = _text_step(expression, organism)
    spec = OperationalSpec(record_type="transcript", criteria=[step])
    domain = StrategyDomainState(operational_spec=spec, answered_spec=spec)
    deps = lead_deps(pipeline_state("tritrypdb", user_prompt=_MESSAGE, domain=domain))
    ctx = run_context_for(deps, tool_call_id="call_classify")
    await classify_user_intent(ctx, user_intent(IntentClassification.EXTEND_STRATEGY))
    card = CardQuestion(id="q1", prompt="Which text term should it use?", options=[])
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_consult", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_consult": [
            UserQuestionAnswer(
                question_id=card.id, prompt=card.prompt, chosen_labels=[], note=_ANSWER
            )
        ]
    }
    await consult_user(
        run_context_for(deps, "call_consult"), questions=[card], reply="One question."
    )
    await classify_user_intent(
        run_context_for(deps, "call_classify_answer"),
        user_intent(
            IntentClassification.CLARIFICATION_RESPONSE,
            explicit_constraints=[
                c for c in (_PHRASE, _VSG, _THE_ORGANISM) if c in stated
            ],
        ),
    )
    return deps


def _stated_keys(deps: LeadDeps) -> list[str]:
    return [c.key for c in deps.state.turn_markers.requirements_added]


def _phrase_change() -> SetValuesChange:
    return SetValuesChange(
        sentence='Search the product text for the phrase "GPI anchored"',
        criterion_id="step_text",
        params={"text_expression": "GPI anchored"},
        answers=[_PHRASE_KEY],
    )


def _vsg_change() -> AddCriterionChange:
    return AddCriterionChange(
        sentence=(
            "Add the variant surface glycoprotein products, joined to the phrase "
            "step by a union"
        ),
        search_name="GenesByText",
        params={"text_expression": "variant surface glycoprotein"},
        answers=[_VSG_KEY],
    )


def _card(
    *changes: ProposedChange, left_to_ask: list[str] | None = None
) -> CardProposal:
    return CardProposal(
        question="Build the phrase search and the VSG arm?",
        proposed_changes=list(changes),
        left_to_ask=list(left_to_ask or []),
        reply="Two arms answer the two parts of your answer.",
    )


async def test_a_card_with_only_the_phrase_is_refused_naming_the_vsg_part() -> None:
    deps = await _answered(_PHRASE, _VSG)

    with pytest.raises(ModelRetry) as refused:
        refuse_a_card_that_leaves_a_part(
            run_context_for(deps, "call_card"), _card(_phrase_change())
        )

    assert (
        '"VSG products" (other:variant surface glycoprotein)' in refused.value.message
    )
    assert '"Phrase"' not in refused.value.message


async def test_the_card_with_the_phrase_and_the_vsg_arm_passes() -> None:
    deps = await _answered(_PHRASE, _VSG)

    refuse_a_card_that_leaves_a_part(
        run_context_for(deps, "call_card"), _card(_phrase_change(), _vsg_change())
    )

    assert _stated_keys(deps) == [_PHRASE_KEY, _VSG_KEY]


async def test_a_phrase_a_step_already_searches_needs_no_change() -> None:
    deps = await _answered(_PHRASE, _VSG, expression="GPI anchored")

    refuse_a_card_that_leaves_a_part(
        run_context_for(deps, "call_card"), _card(_vsg_change())
    )

    assert _stated_keys(deps) == [_PHRASE_KEY, _VSG_KEY]


async def test_an_organism_the_strategy_holds_needs_no_change() -> None:
    deps = await _answered(_PHRASE, _VSG, _THE_ORGANISM)

    refuse_a_card_that_leaves_a_part(
        run_context_for(deps, "call_card"), _card(_phrase_change(), _vsg_change())
    )

    assert _stated_keys(deps) == [_PHRASE_KEY, _VSG_KEY, f"organism:{_ORGANISM}"]


async def test_an_organism_the_strategy_does_not_hold_is_refused() -> None:
    deps = await _answered(
        _PHRASE, _VSG, _THE_ORGANISM, organism="Trypanosoma brucei brucei TREU927"
    )

    with pytest.raises(ModelRetry) as refused:
        refuse_a_card_that_leaves_a_part(
            run_context_for(deps, "call_card"),
            _card(_phrase_change(), _vsg_change()),
        )

    assert f'"Organism" (organism:{_ORGANISM})' in refused.value.message


async def test_a_part_the_card_leaves_to_a_question_passes() -> None:
    deps = await _answered(_PHRASE, _VSG)

    refuse_a_card_that_leaves_a_part(
        run_context_for(deps, "call_card"),
        _card(_phrase_change(), left_to_ask=[_VSG_KEY]),
    )

    assert _stated_keys(deps) == [_PHRASE_KEY, _VSG_KEY]


async def test_a_key_the_thread_does_not_hold_is_refused() -> None:
    deps = await _answered(_PHRASE, _VSG)
    change = _vsg_change().model_copy(update={"answers": ["other:VSG"]})

    with pytest.raises(ModelRetry) as refused:
        refuse_a_card_that_leaves_a_part(
            run_context_for(deps, "call_card"), _card(_phrase_change(), change)
        )

    assert "other:VSG" in refused.value.message
    assert _VSG_KEY in refused.value.message


async def test_a_card_the_researcher_accepted_runs_as_accepted() -> None:
    deps = await _answered(_PHRASE, _VSG)
    ctx = run_context_for(deps, "call_card")
    ctx.tool_call_approved = True

    refuse_a_card_that_leaves_a_part(ctx, _card(_phrase_change()))

    assert _stated_keys(deps) == [_PHRASE_KEY, _VSG_KEY]


def test_the_lead_toolset_checks_the_card_before_it_defers() -> None:
    tools = unwrap_function_toolset(build_lead_toolset()).tools

    assert tools["propose_changes"].args_validator is refuse_a_card_that_leaves_a_part


async def test_a_refused_card_says_the_researcher_never_saw_it() -> None:
    deps = await _answered(_PHRASE, _VSG)

    with pytest.raises(ModelRetry) as refused:
        refuse_a_card_that_leaves_a_part(
            run_context_for(deps, "call_card"), _card(_phrase_change())
        )

    assert refused.value.message.endswith(CARD_NOT_SHOWN)
