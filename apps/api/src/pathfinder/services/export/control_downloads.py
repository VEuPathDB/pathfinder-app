"""Where a control outcome and a parameter sweep download from, once exported."""

from assistant_core.platform.types import JSONObject
from veupathdb import get_logger
from veupathdb.errors import VEuPathDBError
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


async def attach_sweep_download(result_json: JSONObject, search_name: str) -> None:
    """Export a sweep result and name where the export downloads from."""
    try:
        export = await get_export_service().export_json(
            result_json, f"{search_name}_optimization"
        )
    except (VEuPathDBError, OSError) as exc:
        logger.warning("Optimization export failed", error=str(exc))
        return
    result_json["downloads"] = {
        "jsonUrl": export.url,
        "expiresInSeconds": export.expires_in_seconds,
    }
