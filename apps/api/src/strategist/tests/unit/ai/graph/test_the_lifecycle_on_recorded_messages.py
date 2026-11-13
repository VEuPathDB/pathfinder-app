"""The thread derives each requirement's lifecycle from the messages and the
typed statements of recorded conversations on the live sites."""

from __future__ import annotations

from uuid import uuid4

from strategist.ai.graph.thread_requirements import ThreadRequirements
from strategist.ai.graph.turn_records import TurnMarkers
from strategist.ai.lead.intent import IntentClassification, UserIntent
from strategist.domain.strategy.constraints import (
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
        quote=value,
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
    return [(r.constraint.id, r.lifecycle) for r in thread.retired_requirements]


_ORGANISM, _OTHER, _COMBINATION = (
    ConstraintKind.ORGANISM,
    ConstraintKind.UNTYPED,
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

    assert ([c.id for c in thread.requirements], _retired(thread)) == (
        [_HEMOGLOBIN.id, _PF3D7.id],
        [(_GENUS.id, ReplacedLifecycle(by=_PF3D7.id))],
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


def _dropped(*withdrawn: str) -> ThreadRequirements:
    thread = _thread(list(_PF3D7_TM_HELD))
    thread.record(
        _intent(
            IntentClassification.EDIT_STRATEGY,
            asks=[_WITHOUT_TM],
            withdrawn_ids=list(withdrawn),
        ),
        [_DROP_TM],
    )
    return thread


def test_dropping_the_transmembrane_part_withdraws_it_and_replaces_nothing() -> None:
    thread = _dropped(_TM.id)

    assert ([c.id for c in thread.requirements], _retired(thread)) == (
        [_PF3D7.id, _APICOPLAST.id],
        [(_TM.id, WithdrawnLifecycle(turn_id=str(thread.turn_markers.message_id)))],
    )


def test_an_id_the_thread_does_not_hold_withdraws_nothing() -> None:
    thread = _dropped("requirement_unheld")

    assert ([c.id for c in thread.requirements], thread.retired_requirements) == (
        [_PF3D7.id, _APICOPLAST.id, _TM.id],
        [],
    )


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
            withdrawn_ids=[_AMASTIGOTES.id],
        ),
        [_STAGE_SWAP],
    )

    assert ([c.id for c in thread.requirements], _retired(thread)) == (
        [_JPCM5.id, _ZINC.id, _PROMASTIGOTES.id],
        [(_AMASTIGOTES.id, ReplacedLifecycle(by=_PROMASTIGOTES.id))],
    )


# trichdb: a leucine-rich repeat AND a transmembrane domain, then OR.
_G3 = _stated(_ORGANISM, "Trichomonas vaginalis G3")
_LRR = _stated(_OTHER, "leucine-rich repeat domain", "domain requirement")
_TMD = _stated(_OTHER, "transmembrane domain", "domain requirement")
_BOTH = _stated(_COMBINATION, "leucine-rich repeat domain AND transmembrane domain")
_BOTH_ASKED = (
    "Trichomonas vaginalis G3 genes with a leucine-rich repeat domain and a "
    "transmembrane domain."
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

    assert ([c.id for c in thread.requirements], thread.retired_requirements) == (
        [_G3.id, _LRR.id, _TMD.id, _BOTH.id],
        [],
    )
