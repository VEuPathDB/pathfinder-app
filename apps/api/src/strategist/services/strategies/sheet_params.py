"""The parameters each search's sheet shows on one site, and the dependent
vocabularies a step's own parent values answer."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping, Sequence

from assistant_core.platform.logging import get_logger
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    fetch_search_details,
    format_param_info_typed,
    read_search_definition,
    wdk_fetch_at,
)

from strategist.domain.strategy.operational_spec import Criterion
from strategist.domain.strategy.spec_hydration import StepRead, sheet_bound
from strategist.domain.strategy.value_binding import parents_moved
from strategist.services.strategies.record_classes import search_record_types

logger = get_logger(__name__)


async def _listed_under(site_id: str, search_name: str) -> str | None:
    listed = await search_record_types(site_id, [search_name])
    if search_name not in listed:
        logger.warning(
            "the site lists no record type for the search", search_name=search_name
        )
        return None
    return listed[search_name]


type DefinitionRead = Callable[[str, str, str], Awaitable[WDKSearch]]


async def catalog_search_definition(
    site_id: str, record_type: str, search_name: str
) -> WDKSearch:
    """The published definition of the search, read through the catalog.

    The structural parameters and the search properties are both dropped from the
    sheet. The catalog's per-process cache holds site metadata and no user data.
    """
    response, _ = await fetch_search_details(
        SearchContext(site_id, record_type, search_name)
    )
    return response.search_data


async def _parameters_read(
    site_id: str, search_names: Collection[str], read: DefinitionRead
) -> dict[str, list[ParameterInfo]]:
    sheets: dict[str, list[ParameterInfo]] = {}
    for search_name in sorted(set(search_names)):
        try:
            listed_under = await _listed_under(site_id, search_name)
            if listed_under is None:
                continue
            definition = await read(site_id, listed_under, search_name)
        except (VEuPathDBError, OSError) as exc:
            logger.warning(
                "search sheet unreadable",
                search_name=search_name,
                error=str(exc),
            )
            continue
        sheets[search_name] = format_param_info_typed(definition.parameters or [])
    return sheets


async def parameters_of_searches(
    *,
    site_id: str,
    search_names: Collection[str],
) -> dict[str, list[ParameterInfo]]:
    """Every parameter of every search the catalog reads, each read under the
    record type the catalog lists it under.

    A search the catalog lists under no record type, or cannot read, is left
    out, so the caller keeps the values it already holds for that search.
    """
    return await _parameters_read(site_id, search_names, read_search_definition)


async def published_parameters_of_searches(
    *,
    site_id: str,
    search_names: Collection[str],
) -> dict[str, list[ParameterInfo]]:
    return await _parameters_read(site_id, search_names, catalog_search_definition)


async def sheet_params_for_searches(
    *,
    site_id: str,
    search_names: Collection[str],
) -> dict[str, list[ParameterInfo]]:
    """The bindable parameters of each search ``parameters_of_searches`` reads."""
    read = await parameters_of_searches(site_id=site_id, search_names=search_names)
    return {
        name: [info for info in infos if info.bindable] for name, infos in read.items()
    }


def _with_vocabulary(info: ParameterInfo, read: ParameterInfo) -> ParameterInfo:
    """The published entry holding the vocabulary another read answers."""
    return info.model_copy(
        update={
            "allowed_values": read.allowed_values,
            "allowed_values_total": read.allowed_values_total,
            "allowed_values_tree": read.allowed_values_tree,
            "allowed_values_note": read.allowed_values_note,
            "prompt_values": read.prompt_values,
            "vocab_leaves": read.vocab_leaves,
            "filter_fields": read.filter_fields,
            "filter_leaves": read.filter_leaves,
        }
    )


async def vocabularies_under(
    fetch_at: ParamFetcher, infos: list[ParameterInfo], values: Mapping[str, ParamValue]
) -> list[ParameterInfo]:
    """The published sheet with each dependent vocabulary as the bound parents
    answer it. WDK answers each sent value as its parameter's initial value, so
    the read gives vocabularies and nothing else."""
    if not any(info.wire_parents for info in infos):
        return infos
    read = await fetch_at({name: to_wire(value) for name, value in values.items()})
    answered = {info.name: info for info in format_param_info_typed(read)}
    return [
        _with_vocabulary(info, answered[info.name])
        if info.wire_parents and info.name in answered
        else info
        for info in infos
    ]


async def _sheet_under(
    site_id: str,
    search_name: str,
    sheet: Sequence[ParameterInfo],
    values: Mapping[str, ParamValue],
    names: Collection[str],
    record_type: str | None = None,
) -> list[ParameterInfo] | None:
    """The sheet with each dependent vocabulary of these names read under the
    values; None while their parents hold the published values, or when the site
    cannot read it."""
    if not parents_moved(values, names, sheet):
        return None
    try:
        listed_under = record_type or await _listed_under(site_id, search_name)
        if listed_under is None:
            return None
        fetch_at = wdk_fetch_at(site_id, listed_under, search_name)
        return await vocabularies_under(fetch_at, list(sheet), values)
    except (VEuPathDBError, OSError) as exc:
        logger.warning(
            "step vocabulary unreadable", search_name=search_name, error=str(exc)
        )
        return None


async def criterion_sheets(
    site_id: str,
    criteria: Iterable[Criterion],
    sheets: Mapping[str, Sequence[ParameterInfo]],
) -> dict[str, list[ParameterInfo]]:
    """The published sheet of each criterion's search with each dependent
    vocabulary read under the values the criterion holds, by criterion id."""
    read: dict[str, list[ParameterInfo]] = {}
    for c in criteria:
        published = list(sheets.get(c.search_name, []))
        under = await _sheet_under(
            site_id,
            c.search_name,
            published,
            c.param_values,
            [info.name for info in published],
            c.record_class,
        )
        read[c.id] = published if under is None else under
    return read


async def sheets_under_their_parents(
    *,
    site_id: str,
    steps: Iterable[StepRead],
    sheets: Mapping[str, Sequence[ParameterInfo]],
) -> dict[str, list[ParameterInfo]]:
    """The sheet of each step whose dependent picks its own parent values
    answer, by step id. A step whose parents hold the published values reads
    the published sheet, so it is left out, and so is a step the site cannot
    read."""
    under: dict[str, list[ParameterInfo]] = {}
    for step in steps:
        search_name = step.node.search_name
        sheet = sheets.get(search_name)
        if sheet is None:
            continue
        values = sheet_bound(step.node.parameters, sheet)
        read = await _sheet_under(site_id, search_name, sheet, values, step.names)
        if read is not None:
            under[step.node.id] = read
    return under
