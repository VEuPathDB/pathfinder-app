"""A record id with the site's page of its record."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict


class ListedRecord(CamelModel):
    """One id a listing returned, and the site's page of its record."""

    model_config = ConfigDict(frozen=True)

    record_id: str
    url: str


__all__ = ["ListedRecord"]
