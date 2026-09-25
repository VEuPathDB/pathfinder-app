"""A reply states the counts of the offer its card carries, or of the offer the
thread adopted, and of no other offer the thread holds."""

from __future__ import annotations

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.turn_contract import LeadResponse, Mismatch, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.separation import AttachedControls, SeparationOffer
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.separation import (
    ERYTHROCYTE_INVASION,
    TASK_ID,
    recorded_offer,
)
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_STALE_TASK = "0c6100d2-0000-4000-8000-0000000057a1"
_OFFERED = (
    "The closest strategy recovers 61 of 80 positives and admits 2 of 40 "
    "negatives in 1,132 genes. Its GO term for other organism part alone "
    "recovers 42 of 80 positives."
)
# The stale offer's read: 47 of its 80 positives, 2 of its 55 negatives.
_STALE = "An earlier run recovered 47 of 80 positives."


def _stale_offer() -> SeparationOffer:
    return recorded_offer(ERYTHROCYTE_INVASION).model_copy(
        update={"task_id": _STALE_TASK}
    )


def _unbacked(
    prose: str,
    *,
    card_offer: str | None,
    attached: AttachedControls | None = None,
) -> list[Mismatch]:
    offers = [recorded_offer(), _stale_offer()]
    state = pipeline_state(
        domain=StrategyDomainState(
            separation_offers={offer.task_id: offer for offer in offers},
            attached_controls=attached,
        )
    )
    record = turn_record(
        run_context_for(lead_deps(state)), card_offer=card_offer
    ).model_copy(update={"ends_on_a_card": card_offer is not None})
    found = reconcile(LeadResponse(prose=prose, strategy_changed=False), record)
    return [m for m in found if m.kind == "unbacked_evidence"]


def test_a_count_the_offer_does_not_hold_is_denied_naming_both() -> None:
    (denied,) = _unbacked(
        "The closest strategy recovers 78 of 80 positives.", card_offer=str(TASK_ID)
    )

    assert (
        "The reply says 78 of 80 positive controls; the control results recorded "
        "61 of 80 positive controls returned; 42 of 80 positive controls returned; "
        "31 of 80 positive controls returned; 38 of 80 positive controls returned."
    ) in denied.sentence


def test_the_counts_of_the_offer_on_the_card_pass() -> None:
    assert _unbacked(_OFFERED, card_offer=str(TASK_ID)) == []


def test_a_count_of_an_offer_the_card_does_not_carry_is_denied() -> None:
    (denied,) = _unbacked(_STALE, card_offer=str(TASK_ID))

    assert denied.sentence.startswith(
        "The reply says 47 of 80 positive controls returned; the control results "
        "recorded 61 of 80 positive controls returned; 42 of 80 positive controls "
        "returned; 31 of 80 positive controls returned; 38 of 80 positive controls "
        "returned."
    )


def test_the_adopted_offer_backs_a_typed_reply() -> None:
    adopted = AttachedControls(
        task_id=str(TASK_ID),
        control_set_id="5f1c6a2e-0000-4000-8000-00000000c0de",
        positives=["PF3D7_0100600"],
        negatives=["PF3D7_0508800"],
    )

    assert _unbacked(_OFFERED, card_offer=None, attached=adopted) == []
    assert len(_unbacked(_STALE, card_offer=None, attached=adopted)) == 1


def test_a_typed_reply_with_no_adopted_offer_is_backed_by_no_offer() -> None:
    (denied,) = _unbacked(_OFFERED, card_offer=None)

    assert denied.sentence == (
        "The reply says 61 of 80 positive controls, and no control result of this "
        "turn or of its last check holds positive controls. The reply says 2 of 40 "
        "negative controls, and no control result of this turn or of its last "
        "check holds negative controls. The reply says 42 of 80 positive controls, "
        "and no control result of this turn or of its last check holds positive "
        "controls. Control counts and control gene ids are read from the control "
        "tests, the scored comparisons and the sweeps this turn ran, from the "
        "evidence card of the last check, and from the separation offer this "
        "reply's card carries or the conversation adopted. A count of sampled "
        "genes that fit is read from the sample the check judged. Copy them; never "
        "restate one from memory. When none of them holds a result, report no "
        "result. Return the same reply with every control count, control gene id "
        "and sampled-gene count taken from the evidence card, or leave out what "
        "the card does not hold."
    )
