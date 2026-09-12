"""The parameter names each search's sheet shows on one site."""

from __future__ import annotations

from collections.abc import Collection

from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp.catalog import (
    format_param_info_typed,
    read_search_definition,
    resolve_search_record_type,
)

logger = get_logger(__name__)


async def sheet_params_for_searches(
    *,
    site_id: str,
    record_type: str | None,
    search_names: Collection[str],
) -> dict[str, frozenset[str]]:
    """The visible parameter names of every search the catalog reads.

    A search the catalog cannot read is left out, so the caller keeps the
    values it already holds for that search.
    """
    sheets: dict[str, frozenset[str]] = {}
    for search_name in sorted(set(search_names)):
        try:
            listed_under = await resolve_search_record_type(
                site_id, search_name, record_type
            )
            definition = await read_search_definition(
                site_id, listed_under, search_name
            )
        except (VEuPathDBError, OSError) as exc:
            logger.warning(
                "search sheet unreadable",
                search_name=search_name,
                error=str(exc),
            )
            continue
        sheets[search_name] = frozenset(
            info.name
            for info in format_param_info_typed(definition.parameters or [])
            if info.is_visible
        )
    return sheets
