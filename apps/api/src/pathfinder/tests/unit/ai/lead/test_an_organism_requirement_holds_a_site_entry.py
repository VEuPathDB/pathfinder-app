from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from assistant_core.graph.turn_state import UserQuestionAnswer
from pydantic_ai import ModelRetry
from veupathdb_mcp.catalog import (
    DecisionRequest,
    DecisionResponse,
    post_decision,
    use_decisions_transport,
)

from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.frame_requirements import questions_for_the_card
from pathfinder.ai.lead.held_intent import hold_the_intent
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_consult import apply_option_bindings
from pathfinder.ai.lead.sub_agent_dispatch import build_the_spec
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrganismValue,
)
from pathfinder.domain.strategy.organism_picks import OrganismPick, asks_an_organism
from pathfinder.platform.config import get_settings
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_DECISIONS = Path(__file__).parents[3] / "fixtures" / "decisions"
PEST = (
    "Find Anopheles gambiae PEST genes with a predicted signal peptide and 2 to 99 "
    "transmembrane domains."
)
NEOSPORA = "Carry these to their orthologs in Neospora caninum Liverpool."
STRAIN_ALONE = "How many protein-coding genes does 3D7 have?"
SPECIES = "I'm investigating stage-specific expression in Plasmodium falciparum."
MISSPELLED = "Plasmodium falciparium 3D7 genes with a kinase annotation."
PF = "Plasmodium falciparum 3D7"


def _recorded(name: str) -> list[dict[str, Any]]:
    exchanges: list[dict[str, Any]] = json.loads(
        (_DECISIONS / f"{name}.json").read_text()
    )["exchanges"]
    return exchanges


class _Service:
    def __init__(self, exchanges: list[dict[str, Any]]) -> None:
        self.exchanges = list(exchanges)
        self.asked: list[DecisionRequest] = []

    async def __call__(self, request: DecisionRequest) -> DecisionResponse | None:
        self.asked.append(request)
        exchange = self.exchanges.pop(0)
        assert request.model_dump(mode="json") == exchange["request"]
        return DecisionResponse.model_validate(exchange["response"])


async def _unanswered(request: DecisionRequest) -> DecisionResponse | None:
    del request
    return None


@pytest.fixture
def _asks_the_service(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(get_settings(), "pathfinder_chat_provider", "default")
    yield
    use_decisions_transport(post_decision)


def _organism(quote: str, words: str) -> Constraint:
    return Constraint(
        kind=ConstraintKind.ORGANISM,
        requested_value=words,
        label="organism",
        source=ConstraintSource.USER_EXPLICIT,
        quote=quote,
        value=OrganismValue(organism=words),
    )


def _intent(*constraints: Constraint) -> UserIntent:
    return UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="[test] organism",
        explicit_constraints=list(constraints),
    )


def _deps(site_id: str, message: str) -> LeadDeps:
    return lead_deps(pipeline_state(site_id, user_prompt=message))


def _held(deps: LeadDeps) -> list[tuple[str, str | None]]:
    return [
        (c.requested_value, c.organism)
        for c in deps.state.domain.requirements
        if c.kind is ConstraintKind.ORGANISM
    ]


@pytest.mark.usefixtures("recorded_site_organisms")
@pytest.mark.parametrize(
    ("site", "message", "words", "entry"),
    [
        ("vectorbase", PEST, "Anopheles gambiae", "Anopheles gambiae PEST"),
        ("vectorbase", PEST, "Anopheles gambiae PEST", "Anopheles gambiae PEST"),
        ("toxodb", NEOSPORA, "Neospora caninum", "Neospora caninum Liverpool"),
    ],
)
async def test_words_that_complete_to_a_stated_entry_hold_that_entry(
    site: str, message: str, words: str, entry: str
) -> None:
    deps = _deps(site, message)

    await hold_the_intent(deps, _intent(_organism(words, words)), message)

    assert _held(deps) == [(entry, entry)]
    assert deps.state.domain.organism_picks == []


@pytest.mark.usefixtures("recorded_site_organisms", "_asks_the_service")
async def test_a_choice_the_service_settles_holds_its_entry() -> None:
    service = _Service(_recorded("organism_3d7_settles"))
    use_decisions_transport(service)
    deps = _deps("plasmodb", STRAIN_ALONE)

    await hold_the_intent(deps, _intent(_organism("3D7", PF)), STRAIN_ALONE)

    assert _held(deps) == [(PF, PF)]
    assert (len(service.asked), deps.state.domain.organism_picks) == (1, [])


@pytest.mark.usefixtures("recorded_site_organisms", "_asks_the_service")
async def test_a_misspelled_organism_the_choice_settles_holds_its_entry() -> None:
    use_decisions_transport(_Service(_recorded("organism_misspelled_settles")))
    deps = _deps("plasmodb", MISSPELLED)
    words = "Plasmodium falciparium 3D7"

    await hold_the_intent(deps, _intent(_organism(words, words)), MISSPELLED)

    assert _held(deps) == [(PF, PF)]
    assert deps.state.domain.organism_picks == []


@pytest.mark.usefixtures("recorded_site_organisms", "_asks_the_service")
async def test_a_choice_below_the_floor_is_asked_with_its_pick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "decisions_vocab_min_confidence", 0.96)
    use_decisions_transport(_Service(_recorded("organism_misspelled_settles")))
    deps = _deps("plasmodb", MISSPELLED)
    words = "Plasmodium falciparium 3D7"

    await hold_the_intent(deps, _intent(_organism(words, words)), MISSPELLED)

    assert _held(deps) == [(words, None)]
    [pick] = deps.state.domain.organism_picks
    assert (pick.picked, pick.confidence, pick.offered[0]) == (PF, 0.95, PF)


@pytest.mark.usefixtures("recorded_site_organisms", "_asks_the_service")
async def test_a_species_of_several_strains_is_asked_on_the_card() -> None:
    use_decisions_transport(_Service(_recorded("organism_species_unsettled")))
    deps = _deps("plasmodb", SPECIES)
    words = "Plasmodium falciparum"

    await hold_the_intent(deps, _intent(_organism(words, words)), SPECIES)

    domain = deps.state.domain
    assert _held(deps) == [(words, None)]
    assert domain.organism_picks == [
        OrganismPick(
            quote=words,
            offered=[
                PF,
                "Plasmodium falciparum 7G8",
                "Plasmodium falciparum 7G8 2019",
                "Plasmodium falciparum CD01",
                "Plasmodium falciparum Dd2",
            ],
        )
    ]
    [question] = questions_for_the_card(deps, FrameResult(), [])
    assert question.question == (
        'Which organism of this site do you mean by "Plasmodium falciparum"?'
    )
    assert [o.label for o in question.options] == domain.organism_picks[0].offered
    assert (asks_an_organism([question]), asks_an_organism([])) == (True, False)

    domain.record_questions([question])
    apply_option_bindings(
        deps.state,
        [
            UserQuestionAnswer(
                question_id="q1", prompt=question.question, chosen_labels=[PF]
            )
        ],
        sheets={},
    )

    assert _held(deps) == [(PF, PF)]
    assert questions_for_the_card(deps, FrameResult(), []) == []


@pytest.mark.usefixtures("recorded_site_organisms", "_asks_the_service")
async def test_no_answer_from_the_service_is_asked_with_the_nearest_entries() -> None:
    use_decisions_transport(_unanswered)
    deps = _deps("plasmodb", STRAIN_ALONE)

    await hold_the_intent(deps, _intent(_organism("3D7", PF)), STRAIN_ALONE)

    assert _held(deps) == [(PF, None)]
    [pick] = deps.state.domain.organism_picks
    assert (pick.picked, pick.offered[0]) == (None, PF)


@pytest.mark.usefixtures("recorded_site_organisms")
async def test_a_mock_deployment_asks_no_service() -> None:
    service = _Service([])
    use_decisions_transport(service)
    deps = _deps("plasmodb", STRAIN_ALONE)

    await hold_the_intent(deps, _intent(_organism("3D7", PF)), STRAIN_ALONE)
    use_decisions_transport(post_decision)

    assert (service.asked, _held(deps)) == ([], [(PF, None)])


@pytest.mark.usefixtures("recorded_site_organisms")
async def test_a_requirement_with_no_organism_value_is_held_untyped() -> None:
    deps = _deps("plasmodb", SPECIES)
    stored = _organism("Plasmodium falciparum", "Plasmodium falciparum").model_copy(
        update={"value": None}
    )

    await hold_the_intent(deps, _intent(stored), SPECIES)

    assert (_held(deps), deps.state.domain.organism_picks) == (
        [("Plasmodium falciparum", None)],
        [],
    )


async def test_an_intent_with_no_requirement_reads_no_organism_list(
    recorded_site_organisms: list[str],
) -> None:
    deps = _deps("vectorbase", PEST)
    intent = _intent()

    held = await hold_the_intent(deps, intent, PEST)

    assert (recorded_site_organisms, held) == ([], intent)


@pytest.mark.usefixtures("recorded_site_organisms", "_asks_the_service")
async def test_no_build_runs_while_the_card_asks_the_organism() -> None:
    use_decisions_transport(_Service(_recorded("organism_species_unsettled")))
    deps = _deps("plasmodb", SPECIES)
    words = "Plasmodium falciparum"
    await hold_the_intent(deps, _intent(_organism(words, words)), SPECIES)

    with pytest.raises(ModelRetry) as refused:
        await build_the_spec(deps, call_id="call_build")

    assert refused.value.message == (
        "The strategy cannot be built until the researcher names the organism "
        'of "Plasmodium falciparum". Ask the card\'s question; do NOT re-frame.'
    )
