"""Download endpoint for AI-generated export files."""

import io
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from strategist.services.export import get_export_service
from strategist.transport.http.deps import CurrentUser

router = APIRouter(prefix="/api/v1/exports", tags=["exports"])

# Content types the export service emits (see services/export/service.py).
_DOWNLOAD_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Exported file.",
        "content": {
            media_type: {"schema": {"type": "string"}}
            for media_type in (
                "text/csv",
                "text/tab-separated-values",
                "application/json",
                "text/plain",
                "text/markdown",
            )
        },
    }
}


@router.get("/{export_id}", responses=_DOWNLOAD_RESPONSES)
async def download_export(export_id: UUID, user_id: CurrentUser) -> StreamingResponse:
    """Serve a previously generated export file.

    Export IDs are uuid4 tokens with a 10-minute TTL. Requires the
    authenticated user to own the export row.
    """
    svc = get_export_service()
    stored = await svc.get_export(export_id=export_id, user_id=user_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Export not found or expired")
    return StreamingResponse(
        io.BytesIO(stored.data),
        media_type=stored.content_type,
        headers={"Content-Disposition": f'attachment; filename="{stored.filename}"'},
    )
