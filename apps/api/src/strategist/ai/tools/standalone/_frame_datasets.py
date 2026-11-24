from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from pydantic import JsonValue, TypeAdapter, ValidationError
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.domain.strategy.operational_spec import BoundValue
from strategist.domain.strategy.value_source import stated_by_labels, stated_source
from strategist.services.strategies.dataset_sources import id_list, saved_dataset

_IDS: TypeAdapter[list[str]] = TypeAdapter(list[str])


def _ids(value: JsonValue) -> list[str]:
    try:
        return _IDS.validate_python(value, strict=True)
    except ValidationError:
        return []


async def saved_id_lists(
    site_id: str,
    state: AgentToolState,
    call: CriterionCall,
    infos: Sequence[ParameterInfo],
) -> tuple[CriterionCall, dict[str, list[str]]]:
    """The call with each list of ids a dataset parameter states saved on the
    site as an ID list, and the ids each saved list holds."""
    saved: dict[str, JsonValue] = {}
    typed: dict[str, list[str]] = {}
    for info in infos:
        ids = _ids(call.params.get(info.name))
        if info.param_kind != "input-dataset" or not ids:
            continue
        key = (call.criterion_id, info.name, tuple(ids))
        if key not in state.id_list_datasets:
            held = await saved_dataset(site_id, id_list(ids))
            state.id_list_datasets[key] = held.dataset_id
        saved[info.name] = state.id_list_datasets[key]
        typed[info.name] = ids
    return replace(call, params={**call.params, **saved}), typed


def with_typed_ids(
    bound: dict[str, BoundValue],
    typed: dict[str, list[str]],
    request_texts: Sequence[str],
) -> dict[str, BoundValue]:
    labelled = dict(bound)
    for name, ids in typed.items():
        held = bound[name].model_copy(update={"label": ", ".join(ids)})
        run = stated_by_labels(ids, (), request_texts)
        source = stated_source(held.value, run, request_texts, ())
        labelled[name] = held.sourced(source, held.basis) if run else held
    return labelled
