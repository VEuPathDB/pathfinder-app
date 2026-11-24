from __future__ import annotations

import pytest
from assistant_core.graph.turn_state import ConsultOption
from pydantic_ai import ModelRetry

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.card_question import CardQuestion
from strategist.ai.lead.lead_consult import consult_can_ask
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrganismValue,
    OrthologValue,
)
from strategist.tests._support.run_context import run_context_for
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_ORGANISM = Constraint(
    id="d15923587319",
    kind=ConstraintKind.ORGANISM,
    requested_value="Plasmodium falciparum 3D7",
    label="Plasmodium falciparum 3D7",
    source=ConstraintSource.USER_EXPLICIT,
    quote="Plasmodium falciparum 3D7",
    value=OrganismValue(organism="Plasmodium falciparum 3D7"),
)
_SYNTENIC = Constraint(
    id="b637e4b8916a",
    kind=ConstraintKind.ORTHOLOG,
    requested_value="syntenic orthologs in Toxoplasma gondii ME49",
    label="syntenic orthologs in Toxoplasma gondii ME49",
    source=ConstraintSource.USER_EXPLICIT,
    quote="syntenic orthologs in Toxoplasma gondii ME49",
    value=OrthologValue(organisms=["Toxoplasma gondii ME49"], syntenic=True),
)
_PROMPT = "The syntenic-only mapping returned no genes. How should I widen the mapping?"
_DROP = "Drop syntenic orthologs in Toxoplasma gondii ME49"
_KEEP = "Keep syntenic orthologs in Toxoplasma gondii ME49"


def _card(*options: ConsultOption) -> CardQuestion:
    return CardQuestion(
        id="widen_orthology_mapping",
        prompt=_PROMPT,
        kind="single_choice",
        options=list(options),
        dimension=ConstraintKind.ORTHOLOG,
        requirement="R2",
    )


async def _ask(card: CardQuestion) -> None:
    state = pipeline_state(
        "veupathdb",
        user_prompt="Carry these to their syntenic orthologs in Toxoplasma gondii ME49.",
        domain=StrategyDomainState(requirements=[_ORGANISM, _SYNTENIC]),
    )
    await consult_can_ask(
        run_context_for(lead_deps(state), "call_card"), [card], reply="One question."
    )


async def test_the_recorded_card_that_recommends_widening_is_refused() -> None:
    card = _card(
        ConsultOption(
            label="Use all orthologs in Toxoplasma gondii ME49",
            description=(
                "Remove the syntenic-only restriction and retain the requested "
                "target organism."
            ),
            recommended=True,
        ),
        ConsultOption(label="Keep syntenic-only mapping"),
    )

    with pytest.raises(ModelRetry) as refused:
        await _ask(card)

    assert str(refused.value) == (
        "R2 is the researcher's requirement 'syntenic orthologs in Toxoplasma "
        "gondii ME49'. A card offers dropping it as 'Drop syntenic orthologs in "
        "Toxoplasma gondii ME49' and recommends no option that drops or replaces "
        "it: the question recommends 'Use all orthologs in Toxoplasma gondii "
        "ME49'. Recommend 'Keep syntenic orthologs in Toxoplasma gondii ME49' or "
        "no option."
    )


async def test_a_recommended_drop_is_refused_on_any_question() -> None:
    card = CardQuestion(
        id="q",
        prompt="Which evidence should the strategy keep?",
        options=[
            ConsultOption(label=_DROP, recommended=True),
            ConsultOption(label="Keep the transform"),
        ],
    )

    with pytest.raises(ModelRetry):
        await _ask(card)


async def test_the_drop_offered_unrecommended_is_asked() -> None:
    await _ask(_card(ConsultOption(label=_DROP), ConsultOption(label=_KEEP)))


async def test_the_keep_may_be_recommended() -> None:
    await _ask(
        _card(ConsultOption(label=_DROP), ConsultOption(label=_KEEP, recommended=True))
    )
