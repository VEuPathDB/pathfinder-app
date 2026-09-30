"""A card question carries the dimension its answer states, and a question of
the Lead's own is refused on a dimension a recorded binding question holds."""

from __future__ import annotations

from uuid import uuid4

from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.lead_consult import (
    card_questions,
    refuse_a_card_that_binds_nothing,
)
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import OpenQuestion, SlotQuestion
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_ORGANISM = "Entamoeba histolytica HM-1:IMSS"
_OTHER_ORGANISM = "Entamoeba dispar SAW760"


def _secreted() -> Criterion:
    return Criterion(
        id="c_secreted",
        text="secreted",
        search_name="GenesWithSignalPeptide",
        organism_param="organism",
        resolved_params={
            "min_length": BoundValue(value=StringValue(value="20"), source="default")
        },
        param_display_names={"organism": "Organism"},
        open_params=[
            OpenSlot(
                criterion_id="c_secreted",
                param_name="organism",
                param_kind="multi-pick-vocabulary",
            )
        ],
    )


def _organism_question() -> OpenQuestion:
    return SlotQuestion(
        question="Which organism should the secreted genes come from?",
        dimension=ConstraintKind.ORGANISM,
        recommended_value=_ORGANISM,
        criterion_id="c_secreted",
        param_name="organism",
        options=[_ORGANISM, _OTHER_ORGANISM],
    ).typed(_secreted())


def _refusal(*questions: OpenQuestion, card: list[CardQuestion]) -> str:
    state = pipeline_state(
        "amoebadb",
        user_prompt="Secreted cysteine proteases",
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(criteria=[_secreted()]),
            open_questions=list(questions),
        ),
    )
    try:
        refuse_a_card_that_binds_nothing(
            run_context_for(lead_deps(state), "call_card"), card, reply="One question."
        )
    except ModelRetry as refused:
        return str(refused)
    return ""


def test_the_card_carries_the_dimension_of_each_recorded_question() -> None:
    [card] = card_questions([_organism_question()])

    assert (card.prompt, card.dimension, [o.label for o in card.options]) == (
        "Which organism should the secreted genes come from?",
        ConstraintKind.ORGANISM,
        [f"Organism {_ORGANISM}", f"Organism {_OTHER_ORGANISM}"],
    )


def test_a_leads_question_on_the_dimension_a_recorded_question_binds_is_refused() -> (
    None
):
    own = CardQuestion(
        id="q2",
        prompt="Which strain do you want?",
        dimension=ConstraintKind.ORGANISM,
    )

    refusal = _refusal(
        _organism_question(),
        card=[*card_questions([_organism_question()]), own],
    )

    assert "'Which strain do you want?' asks the organism" in refusal


def test_a_leads_organism_question_is_refused_while_a_criterion_names_its_organism() -> (
    None
):
    own = CardQuestion(
        id="q1",
        prompt="Which strain do you want?",
        dimension=ConstraintKind.ORGANISM,
    )

    assert "'Which strain do you want?' asks the organism" in _refusal(card=[own])


def test_a_leads_question_on_a_dimension_no_sheet_holds_is_accepted() -> None:
    own = CardQuestion(
        id="q2",
        prompt="Should the result keep only protein-coding genes?",
        dimension=ConstraintKind.DATA_TYPE,
    )

    assert (
        _refusal(
            _organism_question(),
            card=[*card_questions([_organism_question()]), own],
        )
        == ""
    )
