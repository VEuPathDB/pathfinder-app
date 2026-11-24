"""The parameters each search's sheet shows on one site, and the dependent
vocabularies a step's own parent values answer."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping, Sequence

from assistant_core.platform.logging import get_logger
from pydantic import JsonValue
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    WDKFilterReads,
    fetch_search_details,
    format_param_info_typed,
    organism_parameter_of,
    read_search_definition,
    read_under_parents,
    wdk_fetch_at,
)

from strategist.domain.strategy.operational_spec import Criterion
from strategist.domain.strategy.spec_hydration import StepRead, sheet_bound
from strategist.domain.strategy.value_binding import parents_moved
from strategist.domain.unread import Unread
from strategist.services.site_errors import site_words
from strategist.services.strategies.record_classes import search_record_types

logger = get_logger(__name__)

_UNLISTED = Unread(reason="the site lists the search under no record type")


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


type SheetReads = dict[str, list[ParameterInfo] | Unread]


async def _parameters_read(
    site_id: str, search_names: Collection[str], read: DefinitionRead
) -> SheetReads:
    sheets: SheetReads = {}
    for search_name in sorted(set(search_names)):
        try:
            listed_under = await _listed_under(site_id, search_name)
            if listed_under is None:
                sheets[search_name] = _UNLISTED
                continue
            definition = await read(site_id, listed_under, search_name)
        except (VEuPathDBError, OSError) as exc:
            logger.warning(
                "search sheet unreadable",
                search_name=search_name,
                error=str(exc),
            )
            sheets[search_name] = Unread(reason=site_words(exc))
            continue
        declarations = definition.parameters or []
        sheets[search_name] = format_param_info_typed(
            declarations, organism=await organism_parameter_of(site_id, declarations)
        )
    return sheets


def unread_sheets(reads: SheetReads) -> dict[str, Unread]:
    """Why each sheet that was not read was not read."""
    unread: dict[str, Unread] = {}
    for name, sheet in reads.items():
        match sheet:
            case Unread():
                unread[name] = sheet
            case _:
                pass
    return unread


def read_sheets(reads: SheetReads) -> dict[str, list[ParameterInfo]]:
    """The sheets of the searches that were read."""
    sheets: dict[str, list[ParameterInfo]] = {}
    for name, sheet in reads.items():
        match sheet:
            case Unread():
                continue
            case read:
                sheets[name] = read
    return sheets


async def parameters_of_searches(
    *,
    site_id: str,
    search_names: Collection[str],
) -> SheetReads:
    """Every parameter of every search the catalog reads, each read under the
    record type the catalog lists it under, and why each other search was not
    read."""
    return await _parameters_read(site_id, search_names, read_search_definition)


async def published_parameters_of_searches(
    *,
    site_id: str,
    search_names: Collection[str],
) -> dict[str, list[ParameterInfo]]:
    return read_sheets(
        await _parameters_read(site_id, search_names, catalog_search_definition)
    )


async def sheet_params_for_searches(
    *,
    site_id: str,
    search_names: Collection[str],
) -> dict[str, list[ParameterInfo]]:
    """The bindable parameters of each search the catalog reads. A search it
    does not read is left out, so the caller keeps the values it holds."""
    read = await parameters_of_searches(site_id=site_id, search_names=search_names)
    return {
        name: [info for info in infos if info.bindable]
        for name, infos in read_sheets(read).items()
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
    organism = next((info.name for info in infos if info.organism_param), None)
    answered = {
        info.name: info for info in format_param_info_typed(read, organism=organism)
    }
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
) -> list[ParameterInfo] | Unread | None:
    """The sheet with each dependent vocabulary of these names read under the
    values; None while their parents hold the published values or the search is
    listed nowhere; else why the site did not read it."""
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
        return Unread(
            reason=(
                "the vocabulary under the values it holds was not read: "
                f"{site_words(exc)}"
            )
        )


async def read_card_values(
    site_id: str,
    criterion: Criterion,
    stated: Mapping[str, JsonValue],
    sheet: Sequence[ParameterInfo],
) -> None:
    if not sheet:
        return
    listed_under = criterion.record_class or await _listed_under(
        site_id, criterion.search_name
    )
    if listed_under is None:
        return
    await read_under_parents(
        wdk_fetch_at(site_id, listed_under, criterion.search_name),
        stated,
        WDKFilterReads(site_id, listed_under, criterion.search_name),
        about=None,
        bound=criterion.param_values,
    )


async def criterion_sheets(
    site_id: str,
    criteria: Iterable[Criterion],
    sheets: Mapping[str, Sequence[ParameterInfo]],
) -> SheetReads:
    """The published sheet of each criterion's search with each dependent
    vocabulary read under the values the criterion holds, or why it was not
    read, by criterion id."""
    read: SheetReads = {}
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
        match await _sheet_under(site_id, search_name, sheet, values, step.names):
            case list() as read:
                under[step.node.id] = read
            case _:
                pass
    return under
