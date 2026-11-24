from __future__ import annotations

from uuid import uuid4

from assistant_core.graph.turn_state import UserQuestionAnswer

from strategist.ai.graph.state import PipelineState, StrategyDomainState
from strategist.ai.lead.card_question import CardQuestion
from strategist.ai.lead.lead_consult import apply_option_bindings
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    CountValue,
    OrganismValue,
)
from strategist.domain.strategy.questions import OpenQuestion
from strategist.tests._support.site_organisms import recorded_organisms
from strategist.tests.unit.ai.lead.conftest import pipeline_state

_REQUEST = "Find Plasmodium falciparum 3D7 genes with 30 to 99 transmembrane domains."
_PROMPT = (
    "The requested range returned no genes. Which value should replace the "
    "organism setting for Organism?"
)
_STRAIN = Constraint(
    id="d4acbf561ea7",
    kind=ConstraintKind.ORGANISM,
    requested_value="Plasmodium falciparum 3D7",
    label="Plasmodium falciparum 3D7",
    source=ConstraintSource.USER_EXPLICIT,
    quote="Plasmodium falciparum 3D7",
    value=OrganismValue(organism="Plasmodium falciparum 3D7"),
)
_RANGE = Constraint(
    id="4a10e6ad023d",
    kind=ConstraintKind.COUNT,
    requested_value="30 to 99 transmembrane domains",
    label="30 to 99 transmembrane domains",
    source=ConstraintSource.USER_EXPLICIT,
    quote="30 to 99 transmembrane domains",
    value=CountValue(feature="transmembrane domains", op=">=", value=30),
)
_CARD = CardQuestion(
    id="organism_alternative",
    prompt=_PROMPT,
    kind="free_text",
    dimension=ConstraintKind.ORGANISM,
    requirement="R1",
)


def _answered(note: str) -> PipelineState:
    state = pipeline_state(
        user_prompt=_REQUEST,
        user_message_id=uuid4(),
        domain=StrategyDomainState(
            requirements=[_STRAIN, _RANGE],
            open_questions=[
                OpenQuestion(question=_PROMPT, dimension=ConstraintKind.ORGANISM)
            ],
        ),
    )
    answer = UserQuestionAnswer(
        question_id="organism_alternative",
        prompt=_PROMPT,
        chosen_labels=[],
        note=note,
    )
    apply_option_bindings(
        state,
        [answer],
        [_CARD],
        sheets={},
        organisms=recorded_organisms("plasmodb"),
    )
    return state


def _organisms(state: PipelineState) -> list[tuple[str, str | None]]:
    return [
        (c.requested_value, c.organism)
        for c in state.domain.requirements
        if c.kind is ConstraintKind.ORGANISM
    ]


def test_an_answer_that_names_no_organism_keeps_the_stated_strain() -> None:
    state = _answered("proceed with defaults")

    assert _organisms(state) == [
        ("Plasmodium falciparum 3D7", "Plasmodium falciparum 3D7")
    ]
    assert state.domain.retired_requirements == []


def test_an_organism_typed_that_names_one_site_entry_replaces_it() -> None:
    state = _answered("Plasmodium falciparum 7G8")

    assert _organisms(state) == [
        ("Plasmodium falciparum 7G8", "Plasmodium falciparum 7G8")
    ]
    assert [r.constraint.id for r in state.domain.retired_requirements] == [_STRAIN.id]


def test_an_ambiguous_typed_organism_replaces_nothing() -> None:
    state = _answered("Plasmodium falciparum")

    assert _organisms(state) == [
        ("Plasmodium falciparum 3D7", "Plasmodium falciparum 3D7")
    ]
    assert state.domain.retired_requirements == []
