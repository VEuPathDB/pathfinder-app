"""The text queries a spec binds: the values of free-text parameters that are
not unset, read from the parameter's class and its sheet, never its letters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from assistant_core.platform.logging import get_logger
from veupathdb.domain.parameters import to_wire
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    ParameterInfo,
    format_param_info_typed,
    read_search_definition,
    resolve_search_record_type,
)

from pathfinder.domain.shown_requirements import TextQuery
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.services.strategies.parameter_rules import text_query

logger = get_logger(__name__)


def free_text_params(
    criterion: Criterion, infos: Sequence[ParameterInfo]
) -> frozenset[str]:
    """The parameters of the criterion whose value is a text query."""
    by_name = {info.name: info for info in infos}
    return frozenset(
        name
        for name, held in criterion.resolved_params.items()
        if name in by_name and text_query(by_name[name], held.value)
    )


async def _definition(
    site_id: str, record_type: str, search_name: str
) -> WDKSearch | None:
    try:
        listed_under = await resolve_search_record_type(
            site_id, search_name, record_type
        )
        return await read_search_definition(site_id, listed_under, search_name)
    except (VEuPathDBError, OSError) as exc:
        logger.warning(
            "search sheet unreadable", search_name=search_name, error=str(exc)
        )
        return None


async def search_definitions(
    site_id: str, spec: OperationalSpec | None
) -> dict[str, WDKSearch]:
    """The sheet of each search a bound criterion of the spec runs. A search the
    catalog cannot read has no sheet."""
    if spec is None:
        return {}
    searches = sorted({c.search_name for c in spec.criteria if c.resolved_params})
    read = {
        name: await _definition(site_id, spec.record_type, name) for name in searches
    }
    return {name: sheet for name, sheet in read.items() if sheet is not None}


def text_query_criteria(
    spec: OperationalSpec | None, sheets: Mapping[str, WDKSearch]
) -> list[TextQuery]:
    """The text queries the criteria of the spec bind. A search with no sheet
    binds none."""
    if spec is None:
        return []
    return [
        TextQuery(
            criterion_id=c.id,
            param=name,
            value=to_wire(c.resolved_params[name].value),
        )
        for c in spec.criteria
        if (sheet := sheets.get(c.search_name)) is not None
        for name in sorted(
            free_text_params(c, format_param_info_typed(sheet.parameters or []))
        )
    ]


__all__ = ["free_text_params", "search_definitions", "text_query_criteria"]
