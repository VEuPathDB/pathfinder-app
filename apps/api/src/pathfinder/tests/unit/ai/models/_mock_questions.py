"""A frame pass that leaves one value open and asks it, as the frame tool
answers it and the dispatch hands it to the Lead."""

from __future__ import annotations

from pathfinder.ai.lead.lead_consult import card_questions
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.questions import SlotQuestion
from pathfinder.tests.unit.ai.models._mock_turns import SHEET_ORGANISMS

ASKED_ORGANISM = "Which organism should the signal peptide search read?"
# The name the signal peptide search's sheet shows its organism parameter by.
ORGANISM_LABEL = "Organism"


def asking_frame(site_id: str) -> dict[str, object]:
    """A frame pass that leaves the organism open and asks it with the options
    its sheet offers, the site organism recommended."""
    options = SHEET_ORGANISMS[site_id]
    asked = SlotQuestion(
        question=ASKED_ORGANISM,
        dimension=ConstraintKind.ORGANISM,
        recommended_value=options[0],
        criterion_id="signal_peptide",
        param_name="organism",
        options=options,
    )
    open_slot = Criterion(
        id="signal_peptide",
        text="genes with a predicted signal peptide",
        param_display_names={"organism": ORGANISM_LABEL},
    )
    return {
        "summary": "The signal peptide search needs its organism.",
        "disposition": "needs_user",
        "openQuestions": [asked.model_dump(by_alias=True, mode="json")],
        "cardQuestions": [
            q.model_dump(by_alias=True, mode="json")
            for q in card_questions([asked.typed(open_slot)])
        ],
    }
