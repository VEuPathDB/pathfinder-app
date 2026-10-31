from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import (
    ConsultOption,
    PendingApproval,
    UserQuestionAnswer,
)

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.lead_consult import consult_user
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.chosen_reading import ChosenReading
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_STRAIN = "strain-level counts"
_SPECIES = "species-collapsed counts"
_PROMPT = "Which reading should the strategy answer?"
_BY_YOU = "chosen by you; no card answer of the researcher picked it"


def _deps() -> LeadDeps:
    deps = lead_deps(
        pipeline_state(
            "orthomcl",
            user_prompt="Which Plasmodium has the most singleton genes?",
            user_message_id=uuid4(),
            domain=StrategyDomainState(),
        )
    )
    deps.state.domain.name_reading(
        ChosenReading(chosen=_STRAIN, alternatives=[_SPECIES])
    )
    return deps


def _readings(deps: LeadDeps) -> list[str]:
    summary = derive_ledger(deps.state, None).render_summary().splitlines()
    start = summary.index("## Readings")
    return summary[start + 1 : start + 2]


def test_a_reading_a_pass_built_without_asking_is_shown_as_the_assistants() -> None:
    assert _readings(_deps()) == [
        f"- '{_STRAIN}': {_BY_YOU}; other readings: '{_SPECIES}'"
    ]


def test_a_summary_with_no_reading_has_no_readings_section() -> None:
    deps = lead_deps(pipeline_state("orthomcl", domain=StrategyDomainState()))

    assert "## Readings" not in derive_ledger(deps.state, None).render_summary()


async def test_a_reading_picked_on_a_card_is_shown_as_the_researchers() -> None:
    deps = _deps()
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(
                question_id="q1", prompt=_PROMPT, chosen_labels=[_SPECIES]
            )
        ]
    }
    card = CardQuestion(
        id="q1",
        prompt=_PROMPT,
        dimension=ConstraintKind.OTHER,
        options=[ConsultOption(label=_STRAIN), ConsultOption(label=_SPECIES)],
    )

    await consult_user(run_context_for(deps, "call_card"), [card], reply="Pick one.")

    assert _readings(deps) == [f"- '{_SPECIES}': picked by the researcher on a card"]
