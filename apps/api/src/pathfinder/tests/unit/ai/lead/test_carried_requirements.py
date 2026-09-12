"""What a turn keeps when the previous one ended by asking the user."""

from __future__ import annotations

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.frame_dispatch import frame_work_order
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.domain.strategy.constraints import (
    ConstraintKind,
    OpenQuestion,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
    user_intent,
)

_TURN_ONE = (
    "P. vivax genes that are orthologs of Plasmodium gametocyte-expressed "
    "proteases with non-synonymous SNPs; combine text and GO evidence for "
    "proteases."
)
_TURN_TWO = (
    "The gametocyte RNA-seq study is the one you named second. A SNP counts "
    "when it is non-synonymous. Go ahead and build it."
)
_COMBINATION = "text evidence OR GO evidence"
_STUDY = "Which gametocyte RNA-seq study?"
_STUDY_DEFAULT = "P. falciparum 3D7 gametocyte RNA-seq"
_SNP = "What counts as a SNP?"
_SNP_DEFAULT = "non-synonymous SNPs in P. vivax P01"
_ABANDONED = "Forget that. Find P. falciparum kinases."
_ACCEPTED = "Use the recommended defaults."


def _turn_one_intent() -> UserIntent:
    return user_intent(
        IntentClassification.NEW_STRATEGY,
        inferred_goal="P. vivax orthologs of gametocyte proteases",
        explicit_constraints=[
            requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium vivax"),
            requirement(
                ConstraintKind.COMBINATION,
                "protease evidence combination",
                _COMBINATION,
            ),
        ],
    )


def _asked_state(*questions: OpenQuestion) -> PipelineState:
    """A thread whose first turn stated its request and then asked the user."""
    state = pipeline_state("plasmodb", user_prompt=_TURN_ONE)
    state.domain.record_intent(_turn_one_intent(), request_text=_TURN_ONE)
    state.domain.open_questions = list(questions)
    return state


def _answered(state: PipelineState, text: str, intent: UserIntent) -> PipelineState:
    state.user_prompt = text
    state.domain.record_intent(intent, request_text=text)
    return state


def _questions() -> tuple[OpenQuestion, OpenQuestion]:
    return (
        OpenQuestion(
            question=_STUDY,
            dimension=ConstraintKind.DATA_TYPE,
            recommended_value=_STUDY_DEFAULT,
        ),
        OpenQuestion(
            question=_SNP,
            dimension=ConstraintKind.OTHER,
            recommended_value=_SNP_DEFAULT,
        ),
    )


def _answering_intent() -> UserIntent:
    return user_intent(
        IntentClassification.NEW_STRATEGY,
        inferred_goal="build the P. vivax protease strategy",
        explicit_constraints=[
            requirement(ConstraintKind.DATA_TYPE, "RNA-seq study", "the second one"),
            requirement(ConstraintKind.OTHER, "SNP definition", "non-synonymous"),
        ],
    )


def test_an_answer_to_an_open_question_keeps_the_request_it_answers_for() -> None:
    state = _answered(_asked_state(*_questions()), _TURN_TWO, _answering_intent())

    ledger = derive_ledger(state, _answering_intent())

    values = {g.constraint.requested_value for g in ledger.constraints.grounded}
    assert _COMBINATION in values
    assert "Plasmodium vivax" in values


def test_a_new_goal_with_no_question_open_replaces_the_requirements() -> None:
    fresh = user_intent(
        IntentClassification.NEW_STRATEGY,
        inferred_goal="P. falciparum kinases",
        explicit_constraints=[
            requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
        ],
    )

    state = _answered(_asked_state(), _ABANDONED, fresh)

    ledger = derive_ledger(state, fresh)
    values = {g.constraint.requested_value for g in ledger.constraints.grounded}
    assert _COMBINATION not in values
    assert "Plasmodium falciparum" in values


def _accepting_intent() -> UserIntent:
    return user_intent(
        IntentClassification.CLARIFICATION_RESPONSE,
        inferred_goal="take the recommended defaults",
    )


def test_a_recommendation_the_message_leaves_alone_is_carried() -> None:
    state = _answered(_asked_state(*_questions()), _ACCEPTED, _accepting_intent())

    ledger = derive_ledger(state, _accepting_intent())

    assert [c.requested_value for c in ledger.constraints.recommended] == [
        _STUDY_DEFAULT,
        _SNP_DEFAULT,
    ]


def test_the_pinned_summary_shows_the_carried_recommendations() -> None:
    state = _answered(_asked_state(*_questions()), _ACCEPTED, _accepting_intent())

    summary = derive_ledger(state, _accepting_intent()).render_summary()

    heading = "### Recommended by you, not replaced by the user\n"
    assert summary.split(heading)[-1] == (
        f"- {_STUDY} (data_type): {_STUDY_DEFAULT!r}\n"
        f"- {_SNP} (other): {_SNP_DEFAULT!r}"
    )


def test_a_recommendation_the_message_overrides_is_dropped() -> None:
    state = _answered(_asked_state(*_questions()), _TURN_TWO, _answering_intent())

    ledger = derive_ledger(state, _answering_intent())

    assert ledger.constraints.recommended == []


def test_a_question_with_no_recommendation_carries_nothing() -> None:
    state = _answered(
        _asked_state(OpenQuestion(question=_SNP)),
        _ACCEPTED,
        _accepting_intent(),
    )

    ledger = derive_ledger(state, _accepting_intent())

    assert ledger.constraints.recommended == []


def test_the_frame_dispatch_carries_the_first_turn_combination() -> None:
    state = _answered(_asked_state(*_questions()), _TURN_TWO, _answering_intent())

    deps = agent_deps_for(lead_deps(state, intent=_answering_intent()))

    assert [c.requested_value for c in deps.agent_state.combination_requirements] == [
        _COMBINATION
    ]


def test_the_frame_dispatch_carries_a_recommended_organism() -> None:
    """The thread states no organism, so the recommended one stands."""
    question = OpenQuestion(
        question="Which organism?",
        dimension=ConstraintKind.ORGANISM,
        recommended_value="Plasmodium vivax P01",
    )
    state = pipeline_state("plasmodb", user_prompt="Find the gametocyte proteases.")
    state.domain.open_questions = [question]
    state = _answered(state, _ACCEPTED, _accepting_intent())

    deps = agent_deps_for(lead_deps(state, intent=_accepting_intent()))

    assert deps.agent_state.organism_hints == ["Plasmodium vivax P01"]


def test_the_frame_work_order_names_the_request_the_answer_belongs_to() -> None:
    state = _answered(_asked_state(*_questions()), _TURN_TWO, _answering_intent())

    order = frame_work_order("re-frame with the answers", state)

    assert order == (
        "FRAME work order: re-frame with the answers\n"
        f"User's goal: {_TURN_ONE}\n\nThe user then clarified: {_TURN_TWO}\n"
        "Operationalize into criteria, bind each to a real WDK search, resolve "
        "params, set the structure. Return a FrameResult."
    )


def _waiting_state(*questions: OpenQuestion) -> PipelineState:
    """A thread whose first turn asked the user and recorded the reply's state."""
    state = _asked_state(*questions)
    state.domain.lead_next_state = "await_user"
    return state


def test_a_question_asked_in_prose_alone_still_keeps_the_request() -> None:
    state = _answered(_waiting_state(), _TURN_TWO, _answering_intent())

    ledger = derive_ledger(state, _answering_intent())

    values = {g.constraint.requested_value for g in ledger.constraints.grounded}
    assert _COMBINATION in values
    assert "Plasmodium vivax" in values


def _abandoning_intent() -> UserIntent:
    return user_intent(
        IntentClassification.NEW_STRATEGY,
        inferred_goal="P. falciparum kinases",
        explicit_constraints=[
            requirement(ConstraintKind.ORGANISM, "organism", "Plasmodium falciparum"),
        ],
    )


def test_a_new_goal_while_a_question_is_open_replaces_the_requirements() -> None:
    state = _answered(_waiting_state(*_questions()), _ABANDONED, _abandoning_intent())

    ledger = derive_ledger(state, _abandoning_intent())

    values = {g.constraint.requested_value for g in ledger.constraints.grounded}
    assert _COMBINATION not in values
    assert values == {"Plasmodium falciparum"}


def test_an_abandoned_combination_reaches_no_sub_agent() -> None:
    state = _answered(_waiting_state(*_questions()), _ABANDONED, _abandoning_intent())

    deps = agent_deps_for(lead_deps(state, intent=_abandoning_intent()))

    assert deps.agent_state.combination_requirements == []
    assert deps.agent_state.organism_hints == ["Plasmodium falciparum"]


def _next_question() -> UserIntent:
    return user_intent(
        IntentClassification.CLARIFICATION_RESPONSE,
        inferred_goal="pick the SNP set",
    )


def test_an_accepted_recommendation_outlives_the_next_question() -> None:
    study = OpenQuestion(
        question=_STUDY,
        dimension=ConstraintKind.DATA_TYPE,
        recommended_value=_STUDY_DEFAULT,
    )
    state = _answered(_waiting_state(study), _ACCEPTED, _accepting_intent())

    state.domain.open_questions = [OpenQuestion(question="Which SNP set?")]
    state.domain.record_intent(_next_question(), request_text="And which SNP set?")

    ledger = derive_ledger(state, _next_question())
    assert [c.requested_value for c in ledger.constraints.recommended] == [
        _STUDY_DEFAULT
    ]


def test_a_requirement_stated_earlier_replaces_a_recommendation() -> None:
    strain = OpenQuestion(
        question="Which organism?",
        dimension=ConstraintKind.ORGANISM,
        recommended_value="Plasmodium falciparum",
    )
    state = _answered(_waiting_state(strain), _ACCEPTED, _accepting_intent())

    ledger = derive_ledger(state, _accepting_intent())

    assert ledger.constraints.recommended == []


def test_the_summary_marks_a_requirement_carried_from_an_earlier_message() -> None:
    state = _answered(_waiting_state(), _TURN_TWO, _answering_intent())

    summary = derive_ledger(state, _answering_intent()).render_summary()

    assert (
        f"- protease evidence combination (combination): {_COMBINATION!r} -> "
        "provisional (from an earlier message)"
    ) in summary
    assert "- RNA-seq study (data_type): 'the second one' -> provisional\n" in summary


def _study_only_intent() -> UserIntent:
    """An answer that states a value on one dimension of the two asked about."""
    return user_intent(
        IntentClassification.NEW_STRATEGY,
        inferred_goal="build the P. vivax protease strategy",
        explicit_constraints=[
            requirement(ConstraintKind.DATA_TYPE, "RNA-seq study", "the second one"),
        ],
    )


def test_a_question_that_names_no_dimension_narrows_nothing() -> None:
    state = _waiting_state(
        OpenQuestion(question=_SNP, dimension=ConstraintKind.OTHER),
    )

    state = _answered(state, _TURN_TWO, _study_only_intent())

    values = {
        g.constraint.requested_value
        for g in derive_ledger(state, _study_only_intent()).constraints.grounded
    }
    assert _COMBINATION in values
    assert "Plasmodium vivax" in values


def test_one_question_named_beside_one_unnamed_narrows_nothing() -> None:
    state = _waiting_state(
        OpenQuestion(
            question=_STUDY,
            dimension=ConstraintKind.DATA_TYPE,
            recommended_value=_STUDY_DEFAULT,
        ),
    )
    state.domain.record_questions([OpenQuestion(question=_SNP)])

    state = _answered(state, _ABANDONED, _abandoning_intent())

    values = {
        g.constraint.requested_value
        for g in derive_ledger(state, _abandoning_intent()).constraints.grounded
    }
    assert values == {
        _COMBINATION,
        "Plasmodium vivax",
        "Plasmodium falciparum",
    }


def _frame_questions() -> list[OpenQuestion]:
    """What a FRAME pass leaves open, each naming the dimension it decides."""
    return [
        OpenQuestion(
            question=_STUDY,
            dimension=ConstraintKind.DATA_TYPE,
            recommended_value=_STUDY_DEFAULT,
        ),
        OpenQuestion(
            question=_SNP,
            dimension=ConstraintKind.OTHER,
            recommended_value=_SNP_DEFAULT,
        ),
    ]


def test_a_recorded_frame_question_keeps_the_dimension_it_decides() -> None:
    """A sub-agent's question is recorded typed, not as bare text."""
    state = _waiting_state()

    state.domain.record_questions(_frame_questions())

    assert [
        (q.dimension, q.recommended_value) for q in state.domain.open_questions
    ] == [
        (ConstraintKind.DATA_TYPE, _STUDY_DEFAULT),
        (ConstraintKind.OTHER, _SNP_DEFAULT),
    ]


def test_a_new_goal_replaces_the_requirements_a_frame_question_left_open() -> None:
    """The user abandoned the request, so its criteria reach no sub-agent."""
    state = _waiting_state()
    state.domain.record_questions(_frame_questions())

    state = _answered(state, _ABANDONED, _abandoning_intent())

    ledger = derive_ledger(state, _abandoning_intent())
    values = {g.constraint.requested_value for g in ledger.constraints.grounded}
    assert values == {"Plasmodium falciparum"}
    deps = agent_deps_for(lead_deps(state, intent=_abandoning_intent()))
    assert deps.agent_state.combination_requirements == []
    assert deps.agent_state.organism_hints == ["Plasmodium falciparum"]
