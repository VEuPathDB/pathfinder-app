"""Whether a saved set belongs to the conversation that lists it."""

from uuid import UUID


def saved_here(saved_in: UUID | None, conversation_id: UUID | None) -> bool:
    """True when the set was saved in this conversation."""
    return conversation_id is not None and saved_in == conversation_id
