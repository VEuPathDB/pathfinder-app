"""Step request/response DTOs."""

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field


class PrimaryKeyPart(CamelModel):
    """A single part of a composite WDK primary key."""

    name: str
    value: str


class RecordDetailRequest(CamelModel):
    """Request to fetch a single record by primary key."""

    primary_key: list[PrimaryKeyPart] = Field(min_length=1)
