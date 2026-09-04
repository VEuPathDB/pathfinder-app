"""Control set repository."""

from dataclasses import dataclass, field
from uuid import UUID

from assistant_core.platform.context import calling_application
from sqlalchemy import cast, or_, select
from sqlalchemy.dialects.postgresql import JSONB, array
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.persistence.models import ControlSet


@dataclass
class ControlSetCreate:
    """Data required to create a control set."""

    name: str
    site_id: str
    record_type: str
    positive_ids: list[str]
    negative_ids: list[str]
    source: str | None = None
    tags: list[str] = field(default_factory=list)
    provenance_notes: str | None = None
    is_public: bool = False
    user_id: UUID | None = None


class ControlSetRepository:
    """Control set CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, control_set_id: UUID) -> ControlSet | None:
        """Get control set by ID."""
        return await self.session.get(ControlSet, control_set_id)

    async def list_by_site(
        self,
        site_id: str,
        user_id: UUID | None = None,
        tags: list[str] | None = None,
        limit: int = 100,
    ) -> list[ControlSet]:
        """List control sets for a site, including public ones and user-owned.

        A public set is public to the application that holds it, not to every
        application.
        """
        conditions = [
            ControlSet.site_id == site_id,
            ControlSet.application_id == calling_application(),
        ]
        if user_id is not None:
            conditions.append(
                or_(ControlSet.is_public.is_(True), ControlSet.user_id == user_id)
            )
        else:
            conditions.append(ControlSet.is_public.is_(True))

        if tags:
            conditions.append(cast(ControlSet.tags, JSONB).has_any(array(tags)))

        stmt = (
            select(ControlSet)
            .where(*conditions)
            .order_by(ControlSet.created_at.desc())
            .limit(limit)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, data: ControlSetCreate) -> ControlSet:
        """Create a new control set."""
        cs = ControlSet(
            name=data.name,
            site_id=data.site_id,
            record_type=data.record_type,
            positive_ids=data.positive_ids,
            negative_ids=data.negative_ids,
            source=data.source,
            tags=data.tags,
            provenance_notes=data.provenance_notes,
            is_public=data.is_public,
            user_id=data.user_id,
        )
        self.session.add(cs)
        await self.session.flush()
        return cs
