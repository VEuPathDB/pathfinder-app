"""The count of rows a write statement changed."""

from __future__ import annotations

from typing import cast

from sqlalchemy import CursorResult


def rows_changed(result: object) -> int:
    return cast("CursorResult[object]", result).rowcount or 0
