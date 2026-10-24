"""A stored record this build cannot read loads as no record."""

from __future__ import annotations

from typing import Annotated

from assistant_core.platform.logging import get_logger
from pydantic import ValidationError, ValidatorFunctionWrapHandler, WrapValidator

from pathfinder.domain.column_fit import UNREADABLE_COLUMN_FIT

logger = get_logger(__name__)


def _only_unreadable_fits(error: ValidationError) -> bool:
    return all(e["type"] == UNREADABLE_COLUMN_FIT for e in error.errors())


def refused_when_unreadable(
    value: object, handler: ValidatorFunctionWrapHandler
) -> object:
    try:
        return handler(value)
    except ValidationError as unread:
        if not _only_unreadable_fits(unread):
            raise
        logger.warning("stored verdict refused", reason=UNREADABLE_COLUMN_FIT)
        return None


def emptied_when_unreadable(
    value: object, handler: ValidatorFunctionWrapHandler
) -> object:
    try:
        return handler(value)
    except ValidationError as unread:
        if not _only_unreadable_fits(unread):
            raise
        logger.warning("stored column fits refused", reason=UNREADABLE_COLUMN_FIT)
        return []


type Stored[T] = Annotated[T | None, WrapValidator(refused_when_unreadable)]
type StoredList[T] = Annotated[list[T], WrapValidator(emptied_when_unreadable)]


__all__ = ["Stored", "StoredList"]
