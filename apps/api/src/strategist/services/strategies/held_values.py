from __future__ import annotations

from veupathdb.domain.parameters import HeldValue, ParamValue, value_kind
from veupathdb.domain.strategy import StrategyStep
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import WDKStep
from veupathdb_mcp.catalog import as_tree_leaves

from strategist.domain.unread import Unread
from strategist.services.site_errors import site_words
from strategist.services.strategies.sheet_params import catalog_search_definition
from strategist.services.strategies.site_changes import (
    decoded_on_the_site,
    held_alike,
    wire_of,
)

__all__ = ["values_the_site_holds_otherwise"]


async def values_the_site_holds_otherwise(
    step: StrategyStep, site_step: WDKStep, site_id: str
) -> dict[str, str | None] | Unread:
    wire = wire_of(site_step)
    unmatched = {
        name: value
        for name, value in step.parameters.items()
        if value_kind(value) != "input-step"
        and not (
            name in wire.parameters
            and held_alike(name, value, HeldValue(wire=wire.parameters[name]))
        )
    }
    if not unmatched:
        return {}
    match await _as_sent(unmatched, site_step, site_id):
        case Unread() as unread:
            return unread
        case sent:
            pass
    missing: dict[str, str | None] = {
        name: None for name in sent if name not in wire.parameters
    }
    moved = [
        name
        for name in sent
        if name in wire.parameters
        and not held_alike(name, sent[name], HeldValue(wire=wire.parameters[name]))
    ]
    if not moved:
        return missing
    match await decoded_on_the_site(step.id, site_step.search_name, wire, site_id):
        case Unread(reason=reason):
            return missing or Unread(
                reason=f"the site's values did not decode: {reason}"
            )
        case decoded:
            read = [name for name in moved if name in decoded]
    raw = [name for name in read if value_kind(decoded[name]) is None]
    differing = {
        **missing,
        **{
            name: wire.parameters[name]
            for name in read
            if name not in raw and not held_alike(name, sent[name], decoded[name])
        },
    }
    if differing or not raw:
        return differing
    return Unread(reason=f"the site holds {', '.join(raw)} only as its wire text")


async def _as_sent(
    values: dict[str, ParamValue], site_step: WDKStep, site_id: str
) -> dict[str, ParamValue] | Unread:
    if all(value_kind(v) != "multi-pick-vocabulary" for v in values.values()):
        return values
    try:
        search = await catalog_search_definition(
            site_id, site_step.record_class_name or "", site_step.search_name
        )
    except (VEuPathDBError, OSError) as exc:
        return Unread(
            reason=f"the site did not read the search's parameters: {site_words(exc)}"
        )
    return as_tree_leaves(search.parameters or [], values)
