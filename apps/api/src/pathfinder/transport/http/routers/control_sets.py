"""CRUD endpoints for reusable control gene sets."""

from assistant_core.platform.pydantic_base import CamelModel
from fastapi import APIRouter
from pydantic import Field
from veupathdb.errors import ValidationError

from pathfinder.services.control_sets import (
    ControlSetResponse,
    ControlSetService,
    NewControlSet,
)
from pathfinder.transport.http.deps import CurrentUser, DBSession, SiteIdQuery
from pathfinder.transport.http.schemas.site_id import SiteId

router = APIRouter(prefix="/api/v1/control-sets", tags=["control-sets"])


class CreateControlSetRequest(CamelModel):
    """Payload for creating a new control set."""

    name: str = Field(min_length=1, max_length=255)
    site_id: SiteId
    record_type: str = Field(min_length=1, max_length=100)
    positive_ids: list[str] = Field(default_factory=list)
    negative_ids: list[str] = Field(default_factory=list)
    source: str | None = Field(None, max_length=50)
    tags: list[str] = Field(default_factory=list)
    provenance_notes: str | None = Field(None)
    is_public: bool = Field(default=False)


@router.get("", response_model=list[ControlSetResponse])
async def list_control_sets(
    session: DBSession,
    user_id: CurrentUser,
    site_id: SiteIdQuery = None,
    tags: str | None = None,
) -> list[ControlSetResponse]:
    """List control sets visible to the current user."""
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    if not site_id:
        raise ValidationError(
            title="Missing required parameter",
            detail="siteId query parameter is required",
        )
    return await ControlSetService(session).list_for_site(
        site_id=site_id,
        user_id=user_id,
        tags=tag_list,
    )


@router.post("", response_model=ControlSetResponse, status_code=201)
async def create_control_set(
    body: CreateControlSetRequest,
    session: DBSession,
    user_id: CurrentUser,
) -> ControlSetResponse:
    """Create a new control set."""
    spec = NewControlSet(
        name=body.name,
        site_id=body.site_id,
        record_type=body.record_type,
        positive_ids=body.positive_ids,
        negative_ids=body.negative_ids,
        source=body.source,
        tags=body.tags,
        provenance_notes=body.provenance_notes,
        is_public=body.is_public,
    )
    return await ControlSetService(session).create(spec, user_id=user_id)
