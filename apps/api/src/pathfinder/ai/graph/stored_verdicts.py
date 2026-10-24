"""A stored verdict this build cannot read loads as no verdict."""

from __future__ import annotations

from typing import Annotated

from assistant_core.platform.logging import get_logger
from pydantic import ValidationError, ValidatorFunctionWrapHandler, WrapValidator

from pathfinder.domain.column_fit import UNREADABLE_COLUMN_FIT

logger = get_logger(__name__)


def refused_when_unreadable(
    value: object, handler: ValidatorFunctionWrapHandler
) -> object:
    try:
        return handler(value)
    except ValidationError as unread:
        if not any(e["type"] == UNREADABLE_COLUMN_FIT for e in unread.errors()):
            raise
        logger.warning("stored verdict refused", reason=UNREADABLE_COLUMN_FIT)
        return None


type Stored[T] = Annotated[T | None, WrapValidator(refused_when_unreadable)]


__all__ = ["Stored"]
