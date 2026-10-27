"""A card question carries the dimension its answer states, and a question of
the Lead's own is refused on a dimension a recorded binding question holds."""

from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from pathfinder.ai.lead.recorded_cards import card_questions
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OpenSlot,
)
from pathfinder.domain.strategy.questions import OpenQuestion, SlotQuestion

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


def test_the_card_carries_the_dimension_of_each_recorded_question() -> None:
    [card] = card_questions([_organism_question()])

    assert (card.prompt, card.dimension, [o.label for o in card.options]) == (
        "Which organism should the secreted genes come from?",
        ConstraintKind.ORGANISM,
        [f"Organism {_ORGANISM}", f"Organism {_OTHER_ORGANISM}"],
    )
