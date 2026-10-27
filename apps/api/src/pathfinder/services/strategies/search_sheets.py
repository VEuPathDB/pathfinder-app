from __future__ import annotations

from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import read_search_definition

from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.services.strategies.record_classes import search_record_types

logger = get_logger(__name__)


async def _definition(
    site_id: str, record_type: str, search_name: str
) -> WDKSearch | None:
    try:
        return await read_search_definition(site_id, record_type, search_name)
    except (VEuPathDBError, OSError) as exc:
        logger.warning(
            "search sheet unreadable", search_name=search_name, error=str(exc)
        )
        return None


async def search_definitions(
    site_id: str, spec: OperationalSpec | None
) -> dict[str, WDKSearch]:
    """The sheet of each search a bound criterion of the spec runs, read under the
    record type the catalog lists it under. A search the catalog does not list,
    or cannot read, has no sheet."""
    if spec is None:
        return {}
    searches = sorted({c.search_name for c in spec.criteria if c.resolved_params})
    listed = await search_record_types(site_id, searches)
    read = {
        name: await _definition(site_id, record_type, name)
        for name, record_type in listed.items()
    }
    return {name: sheet for name, sheet in read.items() if sheet is not None}


__all__ = ["search_definitions"]
