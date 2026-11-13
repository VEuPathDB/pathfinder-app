"""Reading a Strategist id out of a tool argument.

The conversation carries WDK numeric ids as well, so a tool that wants a
Strategist UUID has to say so when it gets something else.
"""

from __future__ import annotations

from uuid import UUID

from pydantic_ai.exceptions import ModelRetry


def parse_id_argument(value: str, *, argument: str, names: str) -> UUID:
    """Returns the argument as a UUID, or asks the model for the right id."""
    try:
        return UUID(value)
    except ValueError:
        msg = (
            f"{argument} must be a Strategist {names} id, which is a UUID. "
            f"Got {value!r}. A WDK strategy or step id is a different id and "
            "does not work here."
        )
        raise ModelRetry(msg) from None
