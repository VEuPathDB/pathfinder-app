"""An approved delete withdraws each requirement only the deleted criteria stated."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph.thread_requirements import ThreadRequirements
from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
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
