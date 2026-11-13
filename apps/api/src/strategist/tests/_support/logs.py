"""What a test reads out of the records the tier's logging captured."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator


class LoggedEvent(BaseModel):
    """One captured record, as the configured processor chain leaves it."""

    model_config = ConfigDict(extra="ignore")

    event: str

    @model_validator(mode="before")
    @classmethod
    def _text_is_the_event(cls, value: Any) -> Any:
        """A record a library logs as plain text carries that text as its event."""
        return {"event": value} if isinstance(value, str) else value


def logged_events(
    records: Iterable[logging.LogRecord],
    *,
    logger: str | None = None,
) -> Sequence[str]:
    """The event of each captured record, in order, for one logger or for all."""
    return [
        LoggedEvent.model_validate(record.msg).event
        for record in records
        if logger is None or record.name == logger
    ]
