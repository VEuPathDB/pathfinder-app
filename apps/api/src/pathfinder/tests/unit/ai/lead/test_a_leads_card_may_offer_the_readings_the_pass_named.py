"""A question of the Lead's own may offer the readings a framing pass named, the
one it built and each other, on the dimension other. The researcher's pick, a
turn later, states that reading as a requirement of the thread."""

from __future__ import annotations

from uuid import uuid4

from assistant_core.conversation.serde import build_checkpoint_serde
from assistant_core.graph.turn_state import (
    ConsultOption,
    PendingApproval,
    UserQuestionAnswer,
)

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.lead_consult import (
    consult_user,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.assistants.pathfinder_spec import PATHFINDER_CHECKPOINT_TYPES
from pathfinder.domain.strategy.chosen_reading import ChosenReading
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

_BUILT = "ortholog groups present in at least one represented genome of every species"
_OTHER = "true species-level aggregation of counts across all strains"
_READING = ChosenReading(chosen=_BUILT, alternatives=[_OTHER])
_SPECIES = requirement(ConstraintKind.ORGANISM, "organism scope", "the genus species")
_PROMPT = "Which reading should the strategy answer?"


def _deps() -> LeadDeps:
    deps = lead_deps(
        pipeline_state(
            "orthomcl",
            user_prompt="Aggregate the strains to species level.",
            user_message_id=uuid4(),
            domain=StrategyDomainState(requirements=[_SPECIES]),
        )
    )
    deps.state.domain.name_reading(_READING)
    return deps


def _card(dimension: ConstraintKind, *labels: str) -> CardQuestion:
    return CardQuestion(
        id="q1",
        prompt=_PROMPT,
        dimension=dimension,
        options=[ConsultOption(label=label) for label in labels],
    )


async def test_the_picked_reading_is_a_requirement_beside_the_held_ones() -> None:
    card = _card(ConstraintKind.OTHER, _BUILT, _OTHER)
    deps = _deps()
    deps.state.user_message_id = uuid4()
    deps.state.pending_approval = PendingApproval(
        phase="lead", tool_call_id="call_card", tool_name="consult_user"
    )
    deps.state.user_question_answers = {
        "call_card": [
            UserQuestionAnswer(question_id="q1", prompt=_PROMPT, chosen_labels=[_OTHER])
        ]
    }

    await consult_user(run_context_for(deps, "call_card"), [card], reply="Pick one.")

    assert [(c.kind, c.requested_value) for c in deps.state.domain.requirements] == [
        (ConstraintKind.ORGANISM, "the genus species"),
        (ConstraintKind.OTHER, _OTHER),
    ]
    assert deps.state.researcher_messages() == [
        "Aggregate the strains to species level."
    ]


def test_a_request_set_aside_offers_none_of_its_readings() -> None:
    domain = _deps().state.domain

    domain.set_the_request_aside()

    assert (domain.named_readings, domain.reading_labels()) == ([], [])


def test_the_named_readings_survive_the_checkpoint() -> None:
    domain = _deps().state.domain
    serde = build_checkpoint_serde(PATHFINDER_CHECKPOINT_TYPES)

    restored = serde.loads_typed(serde.dumps_typed(domain))

    assert restored.named_readings == [_READING]
