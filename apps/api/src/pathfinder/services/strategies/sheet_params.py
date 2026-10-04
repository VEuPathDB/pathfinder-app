"""The parameters each search's sheet shows on one site, and the dependent
vocabularies a step's own parent values answer."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence

from assistant_core.platform.logging import get_logger
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.errors import VEuPathDBError
from veupathdb_mcp.catalog import (
    ParameterInfo,
    ParamFetcher,
    format_param_info_typed,
    read_search_definition,
    resolve_search_record_type,
    wdk_fetch_at,
)

from pathfinder.domain.strategy.spec_hydration import StepRead, sheet_bound
from pathfinder.domain.strategy.value_binding import parents_moved

logger = get_logger(__name__)


async def sheet_params_for_searches(
    *,
    site_id: str,
    record_type: str | None,
    search_names: Collection[str],
) -> dict[str, list[ParameterInfo]]:
    """The visible parameters of every search the catalog reads.

    A search the catalog cannot read is left out, so the caller keeps the
    values it already holds for that search.
    """
    sheets: dict[str, list[ParameterInfo]] = {}
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
        sheets[search_name] = [
            info
            for info in format_param_info_typed(definition.parameters or [])
            if info.is_visible
        ]
    return sheets


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
        }
    )


async def vocabularies_under(
    fetch_at: ParamFetcher, infos: list[ParameterInfo], values: Mapping[str, ParamValue]
) -> list[ParameterInfo]:
    """The published sheet with each dependent vocabulary as the bound parents
    answer it. WDK answers each sent value as its parameter's initial value, so
    the read gives vocabularies and nothing else."""
    if not any(info.vocab_depends_on for info in infos):
        return infos
    read = await fetch_at({name: to_wire(value) for name, value in values.items()})
    answered = {info.name: info for info in read}
    return [
        _with_vocabulary(info, answered[info.name])
        if info.vocab_depends_on and info.name in answered
        else info
        for info in infos
    ]


async def sheets_under_their_parents(
    *,
    site_id: str,
    record_type: str | None,
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
        if not parents_moved(values, step.names, sheet):
            continue
        try:
            listed_under = await resolve_search_record_type(
                site_id, search_name, record_type
            )
            fetch_at = wdk_fetch_at(site_id, listed_under, search_name)
            under[step.node.id] = await vocabularies_under(
                fetch_at, list(sheet), values
            )
        except (VEuPathDBError, OSError) as exc:
            logger.warning(
                "step vocabulary unreadable",
                search_name=search_name,
                error=str(exc),
            )
    return under
