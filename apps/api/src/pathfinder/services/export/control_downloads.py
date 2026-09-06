"""Where a control outcome downloads from, once it is exported."""

from veupathdb.errors import VEuPathDBError
from veupathdb.logging import get_logger
from veupathdb_mcp.tool_payloads import ControlOutcome, DownloadLinks

from pathfinder.services.export import get_export_service

logger = get_logger(__name__)


async def attach_control_downloads(
    outcome: ControlOutcome,
    name: str,
) -> ControlOutcome:
    """Export a control outcome and name where the export downloads from."""
    try:
        export = await get_export_service().export_json(
            outcome.model_dump(by_alias=True, exclude_none=True, mode="json"),
            name,
        )
    except (VEuPathDBError, OSError) as exc:
        logger.warning("Control test export failed", error=str(exc))
        return outcome
    outcome.downloads = DownloadLinks(
        json_url=export.url,
        expires_in_seconds=export.expires_in_seconds,
    )
    return outcome
