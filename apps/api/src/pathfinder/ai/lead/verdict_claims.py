"""The contract rule that holds a reply's open values to the question card."""

from __future__ import annotations

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


__all__ = ["open_value_in_prose"]
