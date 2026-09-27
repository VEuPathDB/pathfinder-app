"""The contract rules that hold a reply's control list sizes to the lists the
turn holds, its open values to the question card, and its account of the check
to every gap and caveat the check found, and to a check that stopped."""

from __future__ import annotations

from typing import assert_never

from pathfinder.ai.lead.contract_messages import (
    unstated_caveat_message,
    unstated_gap_message,
    unstated_stop_message,
)
from pathfinder.ai.lead.evidence_claims import (
    ControlList,
    CountClaim,
    count_claims,
    list_claims,
    sample_claims,
    unbacked_list_claims,
)
from pathfinder.ai.lead.turn_record import TurnRecord
from pathfinder.domain.caveats import (
    BuildCaveat,
    Caveat,
    ControlsCaveat,
    SampleCaveat,
)


def _joined(items: list[str]) -> str:
    *head, last = items
    return f"{', '.join(head)} and {last}" if head else last


def _held(lists: tuple[ControlList, ...]) -> str:
    ordered = sorted(lists, key=lambda held: held.kind != "positive")
    return f"{_joined([held.text() for held in ordered])} controls"


def misstated_control_list(prose: str, record: TurnRecord) -> str | None:
    """A count of controls the reply states is a list the turn holds or a
    count a control result backs."""
    wrong = unbacked_list_claims(
        list_claims(prose), record.control_lists, record.control_results
    )
    if not wrong:
        return None
    said = _joined([claim.text() for claim in wrong])
    return (
        f"Your reply says {said}; the lists this turn holds are "
        f"{_held(record.control_lists)}. Return the same reply with each list "
        f"stated at the size the turn holds."
    )


def open_value_in_prose(record: TurnRecord) -> str | None:
    """A value the frame leaves open is asked on the question card."""
    if not record.frame_open_questions or record.ends_on_a_card:
        return None
    asked = _joined([f'"{question}"' for question in record.frame_open_questions])
    each = "it" if len(record.frame_open_questions) == 1 else "each"
    return (
        f"The spec leaves {asked} open. Ask {each} on the question card "
        f"(consult_user) with its options; a question in prose is refused."
    )


def _counts(claim: CountClaim, returned: int, total: int) -> bool:
    """Whether the claim states how many of these controls came back, or how
    many did not."""
    if claim.of != total:
        return False
    if claim.returned is False:
        return claim.stated == total - returned
    return claim.stated == returned


def _controls_stated(prose: str, caveat: ControlsCaveat) -> bool:
    counts = count_claims(prose)
    sets = [
        ("positive", caveat.positives_returned, caveat.positives_total),
        ("negative", caveat.negatives_returned, caveat.negatives_total),
    ]
    short = [caveat.missed_positives(), caveat.returned_negatives()]
    return all(
        any(c.kind == kind and _counts(c, returned, total) for c in counts)
        for (kind, returned, total), falls_short in zip(sets, short, strict=True)
        if falls_short
    )


def _sample_stated(prose: str, caveat: SampleCaveat) -> bool:
    claims = sample_claims(prose)
    wanted = [("unclear", caveat.unclear), ("no", caveat.misfit)]
    return all(
        any(c.fits == fit and c.holds(count, caveat.total) for c in claims)
        for fit, count in wanted
        if count
    )


def caveat_stated(prose: str, caveat: Caveat) -> bool:
    """Whether the prose states the caveat with its numbers."""
    match caveat:
        case ControlsCaveat():
            return _controls_stated(prose, caveat)
        case SampleCaveat():
            return _sample_stated(prose, caveat)
        case BuildCaveat():
            return caveat.stated_by(prose)
        case _:
            assert_never(caveat)


def unstated_gap(prose: str, record: TurnRecord) -> str | None:
    """Every gap of the turn is named in the reply."""
    silent = [gap for gap in record.gaps if not gap.named_by(prose)]
    return unstated_gap_message(silent) if silent else None


def unstated_caveat(prose: str, record: TurnRecord) -> str | None:
    """Every caveat of the turn's check is stated with its numbers."""
    silent = [c for c in record.caveats if not caveat_stated(prose, c)]
    return unstated_caveat_message(silent) if silent else None


def unstated_stop(prose: str, record: TurnRecord) -> str | None:
    """A check of the turn that stopped is stated as unfinished, built or not."""
    stop = record.last_phase_stop
    if stop is None or stop.role != "verification" or stop.stated_by(prose):
        return None
    return unstated_stop_message(stop)


__all__ = [
    "caveat_stated",
    "misstated_control_list",
    "open_value_in_prose",
    "unstated_caveat",
    "unstated_gap",
    "unstated_stop",
]
