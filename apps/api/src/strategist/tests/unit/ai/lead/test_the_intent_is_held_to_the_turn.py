from __future__ import annotations

import pytest

from strategist.ai.graph.turn_records import AnsweredQuestions
from strategist.ai.lead.held_intent import hold_the_intent
from strategist.ai.lead.intent import IntentClassification, NamedControls, UserIntent
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.record_facts import SourceFact
from strategist.domain.strategy.questions import OpenQuestion
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

ATTACHED = (
    "Use these genes as my positive controls.\n"
    "Attached gene-ID list from controls.csv: PF3D7_0709000, PF3D7_1133400"
)
_SHOWN = ("Afu2g18040", "NCU00776")
_START = "Please start the gene-model audit run for these two genes."


def _deps(prompt: str = ATTACHED) -> LeadDeps:
    return lead_deps(pipeline_state(user_prompt=prompt))


def _controls(*positives: str, negatives: tuple[str, ...] = ()) -> UserIntent:
    return UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="Save the researcher's positive controls.",
        named_controls=NamedControls(
            positive_ids=list(positives), negative_ids=list(negatives)
        ),
    )


def _audit_of(*gene_ids: str) -> UserIntent:
    return UserIntent(
        classification=IntentClassification.GENE_MODEL_AUDIT,
        inferred_goal="Start the audit run for the two genes.",
        named_gene_ids=list(gene_ids),
    )


def _shown_deps() -> LeadDeps:
    deps = _deps(_START)
    deps.state.domain.shown_records = [
        SourceFact(url=f"https://example.org/{gene}", record_id=gene) for gene in _SHOWN
    ]
    return deps


async def test_controls_the_attached_list_carries_are_the_turn_s_intent() -> None:
    deps = _deps()
    intent = _controls("PF3D7_0709000", "PF3D7_1133400")

    held = await hold_the_intent(deps, intent, ATTACHED)

    assert (held, deps.intent, deps.state.turn_markers.intent_classified) == (
        intent,
        intent,
        True,
    )


@pytest.mark.parametrize(
    ("positives", "negatives", "kept"),
    [
        (
            ("PF3D7_0709000", "PF3D7_0213400"),
            (),
            NamedControls(positive_ids=["PF3D7_0709000"]),
        ),
        (("PF3D7_0709",), (), NamedControls()),
        (
            ("PF3D7_0709000",),
            ("PF3D7_1133400.1",),
            NamedControls(positive_ids=["PF3D7_0709000"]),
        ),
    ],
)
async def test_a_control_the_message_does_not_hold_is_dropped(
    positives: tuple[str, ...], negatives: tuple[str, ...], kept: NamedControls
) -> None:
    deps = _deps()

    held = await hold_the_intent(
        deps, _controls(*positives, negatives=negatives), ATTACHED
    )

    assert held.named_controls == kept


async def test_ids_the_conversation_showed_last_are_held() -> None:
    deps = _shown_deps()

    held = await hold_the_intent(deps, _audit_of("afu2g18040", *_SHOWN[1:]), _START)

    assert held == _audit_of("afu2g18040", "NCU00776")


async def test_an_id_neither_typed_nor_shown_is_dropped() -> None:
    deps = _shown_deps()

    held = await hold_the_intent(deps, _audit_of(*_SHOWN, "PF3D7_0709000"), _START)

    assert held.named_gene_ids == list(_SHOWN)


async def test_an_answer_closes_the_questions_open_at_arrival() -> None:
    deps = _deps("Use the 2021 study.")
    deps.state.domain.open_questions = [OpenQuestion(question="Which study?")]
    deps.state.turn_markers.questions_at_arrival = ["Which study?"]
    answer = UserIntent(
        classification=IntentClassification.CLARIFICATION_RESPONSE,
        inferred_goal="Use the 2021 study.",
    )

    await hold_the_intent(deps, answer, "Use the 2021 study.")

    assert (deps.state.domain.open_questions, deps.state.turn_markers.answered) == (
        [],
        AnsweredQuestions(
            questions=[OpenQuestion(question="Which study?")],
            answer="Use the 2021 study.",
        ),
    )


async def test_the_recorded_request_is_the_turn_s_own_message() -> None:
    deps = _deps("Find the gametocyte proteases.")
    intent = UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="find the proteases",
    )

    await hold_the_intent(deps, intent, "Find the gametocyte proteases.")

    assert deps.state.domain.original_request == "Find the gametocyte proteases."
