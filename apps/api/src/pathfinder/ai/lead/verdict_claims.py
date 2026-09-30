"""The contract rules that hold a reply's open values to the question card, and
its account of the check to a check that stopped."""

from __future__ import annotations

from pathfinder.ai.lead.contract_messages import unstated_stop_message
from pathfinder.ai.lead.turn_record import TurnRecord


def _joined(items: list[str]) -> str:
    *head, last = items
    return f"{', '.join(head)} and {last}" if head else last


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


def unstated_stop(prose: str, record: TurnRecord) -> str | None:
    """A check of the turn that stopped is stated as unfinished, built or not."""
    stop = record.last_phase_stop
    if stop is None or stop.role != "verification" or stop.stated_by(prose):
        return None
    return unstated_stop_message(stop)


__all__ = ["open_value_in_prose", "unstated_stop"]
