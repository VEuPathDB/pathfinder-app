from __future__ import annotations

import re
from contextlib import AbstractContextManager
from typing import Annotated, Literal
from uuid import UUID, uuid4

import structlog
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

SITE_ID_PATTERN = r"^[a-z][a-z0-9_-]{0,49}$"
_REQUEST_ID = re.compile(r"[A-Za-z0-9-]{1,64}")

SiteLabel = Annotated[str, StringConstraints(pattern=SITE_ID_PATTERN)]
AssistantLabel = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9_-]{0,63}$")]
RouteTemplate = Annotated[
    str, StringConstraints(pattern=r"^/[A-Za-z0-9_./{}-]{0,255}$")
]
HttpMethod = Literal["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]


class LogIds(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    conversation_id: UUID | None = None
    turn_id: UUID | None = None
    user_id: UUID | None = None
    site_id: SiteLabel | None = None
    assistant_id: AssistantLabel | None = None
    run_id: UUID | None = None
    method: HttpMethod | None = None
    route: RouteTemplate | None = None

    @field_validator("site_id", mode="before")
    @classmethod
    def _no_site_is_absent(cls, value: object) -> object:
        return None if value == "" else value

    def named(self) -> dict[str, str]:
        return self.model_dump(mode="json", exclude_none=True)


def log_ids_scope(ids: LogIds) -> AbstractContextManager[None]:
    return structlog.contextvars.bound_contextvars(**ids.named())


def bind_log_ids(ids: LogIds) -> None:
    structlog.contextvars.bind_contextvars(**ids.named())


def accepted_request_id(header: str | None) -> str:
    if header is not None and _REQUEST_ID.fullmatch(header):
        return header
    return str(uuid4())


__all__ = [
    "SITE_ID_PATTERN",
    "LogIds",
    "accepted_request_id",
    "bind_log_ids",
    "log_ids_scope",
]
