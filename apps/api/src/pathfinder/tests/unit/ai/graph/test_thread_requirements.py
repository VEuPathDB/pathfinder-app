"""The thread derives every requirement it holds, replaces and retires from what
a message states and withdraws; an approved delete withdraws each requirement
only the deleted criteria stated."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.ai.graph.thread_requirements import ThreadRequirements
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.question_rows import ResearcherAsk, without_questions
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
    WithdrawnLifecycle,
)
from pathfinder.domain.strategy.operational_spec import Criterion


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=kind.value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_ORGANISM = _stated(ConstraintKind.ORGANISM, "Plasmodium falciparum 3D7")
_TM = _stated(ConstraintKind.OTHER, "a transmembrane domain")
_SIGNAL = _stated(ConstraintKind.OTHER, "a predicted apicoplast targeting signal")
# The plasmodb strategy: the TM step is deleted, the PlasmoAP step stays.
_TM_STEP = Criterion(
    id="step_4dfb1df9",
    text="Plasmodium falciparum 3D7 genes with a transmembrane domain",
    search_name="GenesByTransmembraneDomains",
)
_PLASMOAP_STEP = Criterion(
    id="step_33f64941",
    text="Plasmodium falciparum 3D7 genes with a predicted apicoplast targeting signal",
    search_name=(
        "GenesBySubcellularLocalizationpfal3D7_subcellular_localization_"
        "ApicoplastTargeting_RSRC"
    ),
)


def _thread() -> ThreadRequirements:
    return ThreadRequirements(
        turn_markers=TurnMarkers(message_id=uuid4()),
        requirements=[_ORGANISM, _TM, _SIGNAL],
    )


def test_a_delete_withdraws_what_only_the_deleted_step_stated() -> None:
    thread = _thread()

    thread.retire_what_a_delete_leaves_unanswered([_TM_STEP], [_PLASMOAP_STEP])

    assert (
        thread.requirements,
        [(r.constraint, r.lifecycle) for r in thread.retired_requirements],
    ) == (
        [_ORGANISM, _SIGNAL],
        [
            (
                _TM,
                WithdrawnLifecycle(turn_id=str(thread.turn_markers.message_id)),
            )
        ],
    )


def test_a_delete_never_withdraws_the_organism() -> None:
    """The organism scopes the whole strategy, whatever the remaining text says."""
    thread = _thread()
    remaining = _PLASMOAP_STEP.model_copy(
        update={"text": "a predicted apicoplast targeting signal"}
    )

    thread.retire_what_a_delete_leaves_unanswered([_TM_STEP], [remaining])

    assert thread.requirements == [_ORGANISM, _SIGNAL]


def test_a_requirement_a_remaining_criterion_also_states_survives_a_delete() -> None:
    """The remaining text states the requirement without its article."""
    thread = _thread()
    second_tm = _TM_STEP.model_copy(
        update={"id": "step_tm_max", "text": "transmembrane domain count at most 3"}
    )

    thread.retire_what_a_delete_leaves_unanswered([_TM_STEP], [second_tm])

    assert (thread.requirements, thread.retired_requirements) == (
        [_ORGANISM, _TM, _SIGNAL],
        [],
    )


def _intent(
    classification: IntentClassification = IntentClassification.EDIT_STRATEGY,
    **fields: object,
) -> UserIntent:
    return UserIntent.model_validate(
        {"classification": classification, "inferredGoal": "g"} | fields
    )


def _recorded(
    held: list[Constraint], message: str, intent: UserIntent
) -> ThreadRequirements:
    thread = ThreadRequirements(
        turn_markers=TurnMarkers(message_id=uuid4()), requirements=held
    )
    thread.record(intent, [message])
    return thread


def _lifecycles(thread: ThreadRequirements) -> list[tuple[str, str]]:
    return [
        (r.constraint.requested_value, r.lifecycle.state)
        for r in thread.retired_requirements
    ]


_PLASMODIUM = _stated(ConstraintKind.ORGANISM, "Plasmodium")


def test_a_narrower_organism_replaces_the_held_one_and_keeps_the_constraint() -> None:
    thread = _recorded(
        [_PLASMODIUM, _TM],
        "Make that Plasmodium falciparum 3D7.",
        _intent(explicit_constraints=[_ORGANISM]),
    )

    assert (thread.requirements, thread.retired_requirements[0].lifecycle) == (
        [_TM, _ORGANISM],
        ReplacedLifecycle(by=_ORGANISM.key),
    )


def test_a_withdrawn_requirement_retires_on_its_message() -> None:
    thread = _recorded(
        [_ORGANISM, _TM, _SIGNAL],
        "Drop the transmembrane domain.",
        _intent(withdrawn=[_stated(ConstraintKind.OTHER, "transmembrane domain")]),
    )

    assert (thread.requirements, _lifecycles(thread)) == (
        [_ORGANISM, _SIGNAL],
        [(_TM.requested_value, "withdrawn")],
    )


def test_a_withdrawn_value_the_message_restates_is_replaced_by_it() -> None:
    """The hostdb edit from chromosome 17 to chromosome 19."""
    chromosome_17 = _stated(ConstraintKind.OTHER, "chromosome 17")
    chromosome_19 = _stated(ConstraintKind.OTHER, "chromosome 19")

    thread = _recorded(
        [chromosome_17],
        "Change chromosome 17 to chromosome 19 and tell me the count.",
        _intent(explicit_constraints=[chromosome_19], withdrawn=[chromosome_17]),
    )

    assert (thread.requirements, thread.retired_requirements[0].lifecycle) == (
        [chromosome_19],
        ReplacedLifecycle(by=chromosome_19.key),
    )


def test_a_compared_side_is_never_a_requirement() -> None:
    thread = _recorded(
        [_ORGANISM],
        "How does the count compare with Plasmodium vivax P01?",
        _intent(
            IntentClassification.FOLLOW_UP_QUESTION,
            is_differential=True,
            differential_sides=["Plasmodium falciparum 3D7", "Plasmodium vivax P01"],
            explicit_constraints=[
                _stated(ConstraintKind.ORGANISM, "Plasmodium vivax P01")
            ],
        ),
    )

    assert (thread.requirements, thread.retired_requirements) == ([_ORGANISM], [])


_ASK = "tell me how many have a signal peptide"


def test_an_ask_states_no_requirement() -> None:
    thread = _recorded(
        [_ORGANISM, _TM],
        f"Keep it as it is and {_ASK}.",
        _intent(
            asks=[_ASK],
            explicit_constraints=[_stated(ConstraintKind.OTHER, "signal peptide")],
        ),
    )

    assert (thread.requirements, thread.retired_requirements) == ([_ORGANISM, _TM], [])


def test_an_ask_erases_no_row_it_only_shares_words_with() -> None:
    message = f"Also require a signal peptide and {_ASK}."
    row = RequirementCheck(
        text="a signal peptide", turn=1, how="search", status="unmet"
    )
    review = VerificationReview(requirements=[row])

    kept = without_questions(
        review, [message], [ResearcherAsk(message=message, text=_ASK)]
    )

    assert kept == review


_KINASES = _stated(ConstraintKind.OTHER, "kinases")


def _combination(value: str) -> Constraint:
    return _stated(ConstraintKind.COMBINATION, value)


def test_an_include_verb_records_the_or_as_the_researchers() -> None:
    either = _combination("kinases OR phosphatases")

    thread = _recorded(
        [_KINASES],
        "Broaden the kinases to include phosphatases.",
        _intent(explicit_constraints=[either]),
    )

    assert [(c.key, c.source) for c in thread.requirements] == [
        (_KINASES.key, ConstraintSource.USER_EXPLICIT),
        (either.key, ConstraintSource.USER_EXPLICIT),
    ]


def test_in_addition_to_records_neither_operator_as_the_researchers() -> None:
    message = "Find genes that have a signal peptide in addition to a GPI anchor."
    stated = [
        _combination("signal peptide OR GPI anchor"),
        _combination("signal peptide AND GPI anchor"),
    ]

    theirs = [
        c.requested_value
        for c in _recorded(
            [], message, _intent(explicit_constraints=stated)
        ).requirements
        if c.source is ConstraintSource.USER_EXPLICIT
    ]

    assert theirs == []


def test_a_question_that_names_another_organism_replaces_none() -> None:
    thread = _recorded(
        [_ORGANISM, _TM],
        "And how many of those would Plasmodium vivax P01 have?",
        _intent(
            IntentClassification.FOLLOW_UP_QUESTION,
            explicit_constraints=[
                _stated(ConstraintKind.ORGANISM, "Plasmodium vivax P01")
            ],
        ),
    )

    assert (thread.requirements, thread.retired_requirements) == ([_ORGANISM, _TM], [])


def test_a_count_question_that_asks_for_a_build_states_its_requirements() -> None:
    """An ask that restates the whole message is the request itself."""
    message = "How many Plasmodium falciparum 3D7 genes have a signal peptide?"
    signal = _stated(ConstraintKind.OTHER, "signal peptide")

    thread = _recorded(
        [],
        message,
        _intent(
            IntentClassification.NEW_STRATEGY,
            asks=[message],
            explicit_constraints=[_ORGANISM, signal],
        ),
    )

    assert thread.requirements == [_ORGANISM, signal]


_GS_B = _stated(ConstraintKind.ORGANISM, "Giardia Assemblage B isolate GS_B")
_KINASE_NO_TM = _combination("protein kinase domain AND no transmembrane domain")
_KINASE_STEP = Criterion(
    id="step_kinase",
    text="Giardia Assemblage B isolate GS_B genes with a protein kinase domain",
    search_name="GenesByInterproDomain",
)
_NO_TM_STEP = Criterion(
    id="step_no_tm",
    text="Giardia Assemblage B isolate GS_B genes without a transmembrane domain",
    search_name="GenesByTransmembraneDomains",
)
_REMOVE_THE_EXCLUSION = (
    "Please remove the transmembrane domain exclusion; I want all the protein "
    "kinase domain genes in GS_B whether or not they have a transmembrane domain."
)


def _shown(thread: ThreadRequirements) -> list[tuple[str, list[str]]]:
    return [
        (r.constraint.requested_value, r.shown_requirements())
        for r in thread.retired_requirements
    ]


def test_a_withdrawn_combination_names_no_side_while_its_steps_stand() -> None:
    thread = _recorded(
        [_GS_B, _KINASE_NO_TM],
        _REMOVE_THE_EXCLUSION,
        _intent(withdrawn=[_KINASE_NO_TM]),
    )

    assert (thread.requirements, _shown(thread)) == (
        [_GS_B],
        [(_KINASE_NO_TM.requested_value, [])],
    )


def test_a_delete_names_the_side_of_a_withdrawn_combination_its_step_answered() -> None:
    thread = _recorded(
        [_GS_B, _KINASE_NO_TM],
        _REMOVE_THE_EXCLUSION,
        _intent(withdrawn=[_KINASE_NO_TM]),
    )

    thread.retire_what_a_delete_leaves_unanswered([_NO_TM_STEP], [_KINASE_STEP])

    assert (thread.requirements, _shown(thread)) == (
        [_GS_B],
        [(_KINASE_NO_TM.requested_value, ["no transmembrane domain"])],
    )


def test_a_delete_withdraws_a_live_combination_by_the_side_it_drops() -> None:
    thread = ThreadRequirements(
        turn_markers=TurnMarkers(message_id=uuid4()),
        requirements=[_GS_B, _KINASE_NO_TM],
    )

    thread.retire_what_a_delete_leaves_unanswered([_NO_TM_STEP], [_KINASE_STEP])

    assert (
        thread.requirements,
        [r.lifecycle for r in thread.retired_requirements],
        _shown(thread),
    ) == (
        [_GS_B],
        [WithdrawnLifecycle(turn_id=str(thread.turn_markers.message_id))],
        [(_KINASE_NO_TM.requested_value, ["no transmembrane domain"])],
    )


_SIGNAL_STEP = Criterion(
    id="step_signal",
    text="Giardia Assemblage B isolate GS_B genes with a signal peptide",
    search_name="GenesWithSignalPeptide",
)


@pytest.mark.parametrize(
    ("combination", "deleted", "remaining"),
    [
        pytest.param(
            _KINASE_NO_TM,
            _SIGNAL_STEP,
            [_KINASE_STEP, _NO_TM_STEP],
            id="no-term-names-the-step",
        ),
        pytest.param(
            _combination("protein kinase domain, no transmembrane domain"),
            _NO_TM_STEP,
            [_KINASE_STEP],
            id="no-operator-joins-the-terms",
        ),
    ],
)
def test_a_delete_no_term_of_a_combination_names_leaves_it_live(
    combination: Constraint, deleted: Criterion, remaining: list[Criterion]
) -> None:
    thread = ThreadRequirements(
        turn_markers=TurnMarkers(message_id=uuid4()),
        requirements=[_GS_B, combination],
    )

    thread.retire_what_a_delete_leaves_unanswered([deleted], remaining)

    assert (thread.requirements, thread.retired_requirements) == (
        [_GS_B, combination],
        [],
    )
