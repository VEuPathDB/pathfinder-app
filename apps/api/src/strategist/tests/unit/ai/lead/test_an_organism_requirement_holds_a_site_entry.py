from __future__ import annotations

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

from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.frame_requirements import questions_for_the_card
from strategist.ai.lead.held_intent import hold_the_intent
from strategist.ai.lead.intent import IntentClassification, UserIntent
from strategist.ai.lead.lead_consult import apply_option_bindings
from strategist.ai.lead.sub_agent_dispatch import build_the_spec
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrganismValue,
)
from strategist.domain.strategy.organism_picks import OrganismPick, asks_an_organism
from strategist.platform.config import get_settings
from strategist.tests._support.decisions_wire import ChoosingService
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

PEST = (
    "Find Anopheles gambiae PEST genes with a predicted signal peptide and 2 to 99 "
    "transmembrane domains."
)
NEOSPORA = "Carry these to their orthologs in Neospora caninum Liverpool."
MALARIA = "Which genes of malaria have a signal peptide?"
SPECIES = "I'm investigating stage-specific expression in Plasmodium falciparum."
SPACED = "Kinases of plasmodium  FALCIPARUM 3d7."
PF = "Plasmodium falciparum 3D7"


async def _unanswered(request: DecisionRequest) -> DecisionResponse | None:
    del request
    return None


@pytest.fixture
def _asks_the_service(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(get_settings(), "strategist_chat_provider", "default")
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


TREU927 = "Which Trypanosoma brucei TREU927 protein kinases have a signal peptide?"
UKMEL1 = "Find Cryptosporidium meleagridis UKMEL1 genes with a signal peptide"
LISTER = "Kinases of Trypanosoma brucei Lister 427"


@pytest.mark.usefixtures("recorded_site_organisms")
@pytest.mark.parametrize(
    ("site", "message", "words", "entry"),
    [
        (
            "tritrypdb",
            TREU927,
            "Trypanosoma brucei TREU927",
            "Trypanosoma brucei brucei TREU927",
        ),
        (
            "cryptodb",
            UKMEL1,
            "Cryptosporidium meleagridis UKMEL1",
            "Cryptosporidium meleagridis strain UKMEL1",
        ),
    ],
)
async def test_words_one_entry_holds_in_order_hold_that_entry(
    site: str, message: str, words: str, entry: str
) -> None:
    deps = _deps(site, message)

    await hold_the_intent(deps, _intent(_organism(words, words)), message)

    assert _held(deps) == [(entry, entry)]
    assert deps.state.domain.organism_picks == []


@pytest.mark.usefixtures("recorded_site_organisms", "_asks_the_service")
async def test_words_two_entries_hold_in_order_are_asked_on_the_card() -> None:
    use_decisions_transport(_unanswered)
    deps = _deps("tritrypdb", LISTER)
    words = "Trypanosoma brucei Lister 427"

    await hold_the_intent(deps, _intent(_organism(words, words)), LISTER)

    assert _held(deps) == [(words, None)]
    [pick] = deps.state.domain.organism_picks
    assert {
        "Trypanosoma brucei Lister strain 427",
        "Trypanosoma brucei Lister strain 427 2018",
    } <= set(pick.offered)


@pytest.mark.usefixtures("recorded_site_organisms")
async def test_words_that_fold_to_an_entry_hold_that_entry() -> None:
    deps = _deps("plasmodb", SPACED)
    words = "plasmodium  FALCIPARUM 3d7"

    await hold_the_intent(deps, _intent(_organism(words, words)), SPACED)

    assert _held(deps) == [(PF, PF)]
    assert deps.state.domain.organism_picks == []


@pytest.mark.usefixtures("recorded_site_organisms", "_asks_the_service")
async def test_the_entry_the_service_picks_leads_the_card_and_binds_nothing() -> None:
    service = ChoosingService(PF)
    use_decisions_transport(service)
    deps = _deps("plasmodb", MALARIA)

    await hold_the_intent(deps, _intent(_organism("malaria", "malaria")), MALARIA)

    assert _held(deps) == [("malaria", None)]
    assert len(service.asked) == 1
    assert deps.state.domain.organism_picks == [
        OrganismPick(
            quote="malaria",
            offered=[
                PF,
                "Plasmodium malariae UG01",
                "Plasmodium vivax PAM",
                "Plasmodium vivax P01",
                "Plasmodium vivax PvW1",
            ],
        )
    ]


@pytest.mark.usefixtures("recorded_site_organisms", "_asks_the_service")
@pytest.mark.parametrize(
    ("words", "first"),
    [("P. falciparum", PF), ("malaria", "Plasmodium malariae UG01"), ("3D7", PF)],
)
async def test_no_answer_from_the_service_is_asked_with_the_ranked_entries(
    words: str, first: str
) -> None:
    use_decisions_transport(_unanswered)
    message = f"Which genes of {words} have a signal peptide?"
    deps = _deps("plasmodb", message)

    await hold_the_intent(deps, _intent(_organism(words, words)), message)

    assert _held(deps) == [(words, None)]
    [pick] = deps.state.domain.organism_picks
    assert pick.offered[0] == first


@pytest.mark.usefixtures("recorded_site_organisms", "_asks_the_service")
async def test_a_species_of_several_strains_is_asked_on_the_card() -> None:
    use_decisions_transport(_unanswered)
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
    use_decisions_transport(_unanswered)
    deps = _deps("plasmodb", SPECIES)
    words = "Plasmodium falciparum"
    await hold_the_intent(deps, _intent(_organism(words, words)), SPECIES)

    with pytest.raises(ModelRetry) as refused:
        await build_the_spec(deps, call_id="call_build")

    assert refused.value.message == (
        "The strategy cannot be built until the researcher names the organism "
        'of "Plasmodium falciparum". Ask the card\'s question; do NOT re-frame.'
    )
