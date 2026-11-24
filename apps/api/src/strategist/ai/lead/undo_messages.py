from __future__ import annotations


def no_earlier_revision_message() -> str:
    """The failure of an undo on a thread with no strategy before the last change."""
    return (
        "Nothing to undo: the conversation holds no strategy before the last change. "
        "Removing the strategy is clear_strategy, on the researcher's word."
    )


def nothing_to_undo_message() -> str:
    """The failure of an undo over a strategy already at its previous revision."""
    return (
        "Nothing to undo: the strategy is the one before the last change. Tell "
        "the researcher so, and change nothing."
    )


def undo_moves_nothing_message() -> str:
    """The failure of an undo whose previous revision no criterion can state."""
    return (
        "Nothing to undo that an edit can state: the strategy before the last "
        "change differs from this one only in values no criterion states. Tell "
        "the researcher so, and change nothing."
    )


def unreadable_revision_message(reason: str) -> str:
    return (
        "Nothing was undone: the revision before the last change does not parse, "
        f"so the strategy cannot go back to it: {reason}"
    )
