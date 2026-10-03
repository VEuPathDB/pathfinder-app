"""The thread derives each requirement's lifecycle from the messages and the
typed statements of recorded conversations on the live sites."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph.thread_requirements import ThreadRequirements
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ReplacedLifecycle,
    WithdrawnLifecycle,
)


def _stated(kind: ConstraintKind, value: str, label: str = "") -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=label or kind.value,
        source=ConstraintSource.USER_EXPLICIT,
    )


def _intent(classification: IntentClassification, **fields: object) -> UserIntent:
    return UserIntent.model_validate(
        {"classification": classification, "inferredGoal": "g"} | fields
    )


def _thread(held: list[Constraint]) -> ThreadRequirements:
    return ThreadRequirements(
        turn_markers=TurnMarkers(message_id=uuid4()), requirements=held
    )


def _retired(thread: ThreadRequirements) -> list[tuple[str, object]]:
    return [(r.constraint.key, r.lifecycle) for r in thread.retired_requirements]


_ORGANISM, _OTHER, _COMBINATION = (
    ConstraintKind.ORGANISM,
    ConstraintKind.OTHER,
    ConstraintKind.COMBINATION,
)

# plasmodb: hemoglobin catabolic process across the genus, then one strain.
_GENUS = _stated(_ORGANISM, "Plasmodium")
_HEMOGLOBIN = _stated(_OTHER, "GO term 'hemoglobin catabolic process'")
_PF3D7 = _stated(_ORGANISM, "Plasmodium falciparum 3D7")
_HEMOGLOBIN_ASKED = (
    "Genes across Plasmodium with the GO term 'hemoglobin catabolic process'."
)
_BEFORE_THE_NARROWING = (
    "tell me how many genes there were across Plasmodium before the narrowing"
)
_NARROWED = (
    "Thanks. Please narrow this to Plasmodium falciparum 3D7 only. And tell me "
    "how many genes there were across Plasmodium before the narrowing, so I can "
    "compare."
)


def test_a_narrowed_organism_replaces_the_genus_and_keeps_the_go_term() -> None:
    thread = _thread([_GENUS, _HEMOGLOBIN])

    thread.record(
        _intent(
            IntentClassification.EXTEND_STRATEGY,
            asks=[_BEFORE_THE_NARROWING, "so I can compare"],
            is_differential=True,
            differential_sides=[
                "existing search across Plasmodium before narrowing",
                "same search restricted to Plasmodium falciparum 3D7",
            ],
            explicit_constraints=[_PF3D7],
        ),
        [_NARROWED, _HEMOGLOBIN_ASKED],
    )

    assert ([c.key for c in thread.requirements], _retired(thread)) == (
        [_HEMOGLOBIN.key, _PF3D7.key],
        [(_GENUS.key, ReplacedLifecycle(by=_PF3D7.key))],
    )


# plasmodb: apicoplast targeting and a transmembrane domain, then the TM dropped.
_APICOPLAST = _stated(_OTHER, "predicted apicoplast targeting signal")
_TM = _stated(_OTHER, "a transmembrane domain")
_PF3D7_TM_HELD = [_PF3D7, _APICOPLAST, _TM]
_WITHOUT_TM = "How many genes would I get without the transmembrane domain requirement"
_DROP_TM = (
    "Thanks. How many genes would I get without the transmembrane domain "
    "requirement, just the apicoplast-targeted ones? If that's the better "
    "starting point, feel free to drop the transmembrane part."
)


def _dropped(withdrawn_value: str) -> ThreadRequirements:
    thread = _thread(list(_PF3D7_TM_HELD))
    thread.record(
        _intent(
            IntentClassification.EDIT_STRATEGY,
            asks=[_WITHOUT_TM],
            withdrawn=[_stated(_OTHER, withdrawn_value)],
        ),
        [_DROP_TM],
    )
    return thread


def test_dropping_the_transmembrane_part_withdraws_it_and_replaces_nothing() -> None:
    thread = _dropped("a transmembrane domain")

    assert ([c.key for c in thread.requirements], _retired(thread)) == (
        [_PF3D7.key, _APICOPLAST.key],
        [(_TM.key, WithdrawnLifecycle(turn_id=str(thread.turn_markers.message_id)))],
    )


def test_a_withdrawal_names_the_held_value_without_its_article() -> None:
    """A statement that carries every content word of a held value names it."""
    thread = _dropped("transmembrane domain requirement")

    assert [c.key for c in thread.requirements] == [_PF3D7.key, _APICOPLAST.key]


# tritrypdb: a zinc finger domain expressed in amastigotes, then promastigotes.
_JPCM5 = _stated(_ORGANISM, "Leishmania infantum JPCM5")
_ZINC = _stated(_OTHER, "zinc finger domain", "domain")
_AMASTIGOTES = _stated(_OTHER, "expressed in amastigotes", "expression condition")
_PROMASTIGOTES = _stated(_OTHER, "expressed in promastigotes", "expression condition")
_STAGE_SWAP = (
    "Thanks. Actually, change the stage to promastigotes instead of amastigotes, "
    "keeping the zinc finger part the same."
)


def test_a_changed_stage_replaces_the_stage_and_leaves_the_domain() -> None:
    thread = _thread([_JPCM5, _ZINC, _AMASTIGOTES])

    thread.record(
        _intent(
            IntentClassification.EDIT_STRATEGY,
            explicit_constraints=[_PROMASTIGOTES, _ZINC],
            withdrawn=[_AMASTIGOTES],
        ),
        [_STAGE_SWAP],
    )

    assert ([c.key for c in thread.requirements], _retired(thread)) == (
        [_JPCM5.key, _ZINC.key, _PROMASTIGOTES.key],
        [(_AMASTIGOTES.key, ReplacedLifecycle(by=_PROMASTIGOTES.key))],
    )


# trichdb: a leucine-rich repeat AND a transmembrane domain, then OR.
_G3 = _stated(_ORGANISM, "Trichomonas vaginalis G3")
_LRR = _stated(_OTHER, "leucine-rich repeat domain", "domain requirement")
_TMD = _stated(_OTHER, "transmembrane domain", "domain requirement")
_BOTH = _stated(_COMBINATION, "leucine-rich repeat domain AND transmembrane domain")
_EITHER = _stated(_COMBINATION, "leucine-rich repeat domain OR transmembrane domain")
_BOTH_ASKED = (
    "Trichomonas vaginalis G3 genes with a leucine-rich repeat domain and a "
    "transmembrane domain."
)
_MAKE_IT_OR = (
    "Actually, can you make it OR instead of AND? I want genes that have either "
    "a leucine-rich repeat domain or a transmembrane domain."
)


def test_two_other_values_stated_together_both_stand() -> None:
    thread = _thread([])

    thread.record(
        _intent(
            IntentClassification.NEW_STRATEGY,
            explicit_constraints=[_G3, _LRR, _TMD, _BOTH],
        ),
        [_BOTH_ASKED],
    )

    assert ([c.key for c in thread.requirements], thread.retired_requirements) == (
        [_G3.key, _LRR.key, _TMD.key, _BOTH.key],
        [],
    )


def test_or_instead_of_and_replaces_the_combination_and_keeps_both_terms() -> None:
    thread = _thread([_G3, _LRR, _TMD, _BOTH])

    thread.record(
        _intent(
            IntentClassification.EDIT_STRATEGY,
            explicit_constraints=[_G3, _EITHER, _LRR, _TMD],
        ),
        [_MAKE_IT_OR, _BOTH_ASKED],
    )

    assert (
        [(c.key, c.source) for c in thread.requirements],
        _retired(thread),
    ) == (
        [
            (_G3.key, ConstraintSource.USER_EXPLICIT),
            (_LRR.key, ConstraintSource.USER_EXPLICIT),
            (_TMD.key, ConstraintSource.USER_EXPLICIT),
            (_EITHER.key, ConstraintSource.USER_EXPLICIT),
        ],
        [(_BOTH.key, ReplacedLifecycle(by=_EITHER.key))],
    )


# microsporidiadb: a signal peptide without an ortholog, then a comparison.
_INTESTINALIS = _stated(_ORGANISM, "Encephalitozoon intestinalis ATCC 50506")
_SIGNAL = _stated(_OTHER, "signal peptide")
_NO_ORTHOLOG = _stated(_OTHER, "no ortholog in Encephalitozoon cuniculi GB-M1")


_BOTH_SIDES = (
    "signal peptide requirement plus no ortholog in Encephalitozoon cuniculi GB-M1"
)
_WITHOUT_ORTHOLOGS = (
    "Just a question, don't change anything: how many genes would there be "
    "without the ortholog filter, i.e. only the signal peptide requirement?"
)


def test_a_compared_side_records_no_requirement() -> None:
    held = [_INTESTINALIS, _SIGNAL, _NO_ORTHOLOG]
    thread = _thread(list(held))

    thread.record(
        _intent(
            IntentClassification.FOLLOW_UP_QUESTION,
            asks=["how many genes would there be without the ortholog filter"],
            is_differential=True,
            differential_sides=["signal peptide requirement only", _BOTH_SIDES],
            explicit_constraints=[
                _INTESTINALIS,
                _stated(_OTHER, "signal peptide requirement only"),
            ],
        ),
        [_WITHOUT_ORTHOLOGS],
    )

    assert (thread.requirements, thread.retired_requirements) == (held, [])


# giardiadb: a count question about an exact product phrase.
_MURIS = _stated(_ORGANISM, "Giardia muris Roberts-Thompson")
_CYSTEINE = _stated(_OTHER, "cysteine-rich protein annotation")
_EXACT_PHRASE_ASK = (
    "How many genes actually have the exact phrase 'cysteine-rich protein' in "
    "their product description?"
)


_EXACT_PHRASE_MESSAGE = (
    "Wait, 4,497 genes before the exclusion seems like almost the whole G. muris "
    f"genome. {_EXACT_PHRASE_ASK} Just tell me, don't change the strategy yet."
)


def test_values_only_an_ask_carries_record_nothing() -> None:
    held = [_MURIS, _CYSTEINE]
    thread = _thread(list(held))

    thread.record(
        _intent(
            IntentClassification.FOLLOW_UP_QUESTION,
            asks=[_EXACT_PHRASE_ASK],
            explicit_constraints=[
                _stated(_OTHER, "exact phrase 'cysteine-rich protein'"),
                _stated(_OTHER, "product description"),
            ],
        ),
        [_EXACT_PHRASE_MESSAGE],
    )

    assert (thread.requirements, thread.retired_requirements) == (held, [])
