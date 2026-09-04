"""Control-set service: CRUD + response shaping over the repository.

Transport calls this service; it never touches the repository or ORM model
directly.
"""

from uuid import UUID

from assistant_core.platform.context import calling_application
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import ControlSet
from pathfinder.persistence.repositories.control_set import (
    ControlSetCreate,
    ControlSetRepository,
)
from pathfinder.platform.errors import NotFoundError
from pathfinder.platform.uuid_utils import format_uuid


class NewControlSet(CamelModel):
    """Service-level input for creating a control set."""

    name: str
    site_id: str
    record_type: str
    positive_ids: list[str] = Field(default_factory=list)
    negative_ids: list[str] = Field(default_factory=list)
    source: str | None = None
    tags: list[str] = Field(default_factory=list)
    provenance_notes: str | None = None
    is_public: bool = False


class ControlSetResponse(CamelModel):
    """Serialized control set returned to the client."""

    id: str
    name: str
    site_id: str
    record_type: str
    positive_ids: list[str]
    negative_ids: list[str]
    source: str | None = None
    tags: list[str]
    provenance_notes: str | None = None
    version: int
    is_public: bool
    user_id: str | None = None
    created_at: str


def _serialize(cs: ControlSet) -> ControlSetResponse:
    return ControlSetResponse(
        id=str(cs.id),
        name=cs.name,
        site_id=cs.site_id,
        record_type=cs.record_type,
        positive_ids=[str(x) for x in (cs.positive_ids or [])],
        negative_ids=[str(x) for x in (cs.negative_ids or [])],
        source=cs.source,
        tags=[str(x) for x in (cs.tags or [])],
        provenance_notes=cs.provenance_notes,
        version=cs.version,
        is_public=cs.is_public,
        user_id=format_uuid(cs.user_id),
        created_at=cs.created_at.isoformat() if cs.created_at else "",
    )


def _visible_to(cs: ControlSet, user_id: UUID) -> bool:
    """A public set is readable by every user of the application that holds it."""
    if cs.application_id != calling_application():
        return False
    return cs.is_public or cs.user_id == user_id


class ControlSetService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ControlSetRepository(session)

    async def list_for_site(
        self,
        *,
        site_id: str,
        user_id: UUID,
        tags: list[str] | None,
    ) -> list[ControlSetResponse]:
        rows = await self._repo.list_by_site(
            site_id=site_id,
            user_id=user_id,
            tags=tags,
        )
        return [_serialize(r) for r in rows]

    async def get(self, control_set_id: UUID, user_id: UUID) -> ControlSetResponse:
        cs = await self._repo.get_by_id(control_set_id)
        if cs is None or not _visible_to(cs, user_id):
            raise NotFoundError(title="Control set not found")
        return _serialize(cs)

    async def create(
        self,
        spec: NewControlSet,
        *,
        user_id: UUID,
    ) -> ControlSetResponse:
        cs = await self._repo.create(
            ControlSetCreate(
                name=spec.name,
                site_id=spec.site_id,
                record_type=spec.record_type,
                positive_ids=spec.positive_ids,
                negative_ids=spec.negative_ids,
                source=spec.source,
                tags=spec.tags or [],
                provenance_notes=spec.provenance_notes,
                is_public=spec.is_public,
                user_id=user_id,
            ),
        )
        return _serialize(cs)
