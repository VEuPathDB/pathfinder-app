from __future__ import annotations

import pytest
from assistant_core.graph.turn_state import UserQuestionAnswer

from pathfinder.ai.graph import _lead_reading
from pathfinder.ai.graph._lead_capture import LeadRunCapture
from pathfinder.ai.graph._lead_reading import read_the_words
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
    user_intent,
)

pytestmark = pytest.mark.usefixtures("recorded_site_organisms")

_MESSAGE = "Find the GPI-anchored surface proteins of Trypanosoma congolense IL3000"
_NOTE = (
    'use the phrase "GPI anchored", and also include the variant surface '
    "glycoprotein products"
)
_ANSWER = user_intent(
    IntentClassification.CLARIFICATION_RESPONSE,
    explicit_constraints=[
        requirement(ConstraintKind.UNTYPED, "Phrase", "GPI anchored"),
        requirement(
            ConstraintKind.UNTYPED, "VSG products", "variant surface glycoprotein"
        ),
    ],
)


def _resumed(note: str) -> LeadDeps:
    deps = lead_deps(pipeline_state("tritrypdb", user_prompt=_MESSAGE))
    deps.state.user_question_answers = {
        "call_consult": [
            UserQuestionAnswer(
                question_id="q1", prompt="Which text term?", chosen_labels=[], note=note
            )
        ]
    }
    return deps


def _reading(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    read: list[str] = []

    def _scripted(state: PipelineState, words: str) -> UserIntent:
        del state
        read.append(words)
        return _ANSWER

    monkeypatch.setattr(_lead_reading, "scripted_intent", _scripted)
    return read


async def test_a_card_note_is_read_and_its_requirements_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = _reading(monkeypatch)
    deps = _resumed(_NOTE)

    await read_the_words(
        deps.state,
        deps,
        new_message=False,
        model_id="mock:lead",
        capture=LeadRunCapture(),
    )

    assert read == [_NOTE]
    assert [
        (c.requested_value, c.source.value)
        for c in deps.state.turn_markers.requirements_added
    ] == [
        ("GPI anchored", "user_explicit"),
        ("variant surface glycoprotein", "user_explicit"),
    ]


async def test_a_card_answered_with_no_note_reads_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = _reading(monkeypatch)
    deps = _resumed("")

    await read_the_words(
        deps.state,
        deps,
        new_message=False,
        model_id="mock:lead",
        capture=LeadRunCapture(),
    )

    assert (read, deps.intent) == ([], None)
