from __future__ import annotations

from collections.abc import Sequence

from pydantic import TypeAdapter, ValidationError
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import InputDatasetValue
from veupathdb_mcp.catalog import OverrideMap, ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.domain.strategy.operational_spec import BoundValue
from pathfinder.domain.strategy.value_source import stated_by_labels
from pathfinder.services.strategies.dataset_sources import (
    id_list,
    names_a_dataset,
    saved_dataset,
    typed_ids,
)

_TYPED_FORM: TypeAdapter[InputDatasetValue] = TypeAdapter(InputDatasetValue)


async def saved_id_lists(
    site_id: str,
    state: AgentToolState,
    criterion_id: str,
    infos: Sequence[ParameterInfo],
    overrides: OverrideMap,
) -> tuple[OverrideMap, dict[str, list[str]]]:
    datasets = {info.name for info in infos if info.param_kind == "input-dataset"}
    saved = dict(overrides)
    typed: dict[str, list[str]] = {}
    for name, proposed in overrides.items():
        if name not in datasets:
            continue
        match _read(name, _text(proposed)):
            case InputDatasetValue(dataset_id=dataset_id):
                saved[name] = dataset_id
            case list() as ids:
                key = (criterion_id, name, tuple(ids))
                if key not in state.id_list_datasets:
                    held = await saved_dataset(site_id, id_list(ids))
                    state.id_list_datasets[key] = held.dataset_id
                saved[name] = state.id_list_datasets[key]
                typed[name] = ids
    return saved, typed


def _text(proposed: str | list[str]) -> str:
    match proposed:
        case str():
            return proposed
        case list():
            return " ".join(proposed)


def _typed_form(text: str) -> InputDatasetValue | None:
    try:
        return _TYPED_FORM.validate_json(text)
    except ValidationError:
        return None


def _read(name: str, text: str) -> InputDatasetValue | list[str]:
    named = _typed_form(text)
    if named is not None and names_a_dataset(named.dataset_id):
        return named
    carried = text if named is None else named.dataset_id
    ids = typed_ids(carried)
    if not ids or carried.lstrip().startswith("{"):
        msg = (
            f"{name} takes the ids separated by commas or spaces, or a dataset id "
            f'as {{"type": "input-dataset", "datasetId": "<id>"}}; it read neither '
            f"in {text!r}. Nothing was recorded."
        )
        raise ModelRetry(msg)
    return ids


def with_typed_ids(
    bound: dict[str, BoundValue],
    typed: dict[str, list[str]],
    request_texts: Sequence[str],
) -> dict[str, BoundValue]:
    labelled = dict(bound)
    for name, ids in typed.items():
        held = bound[name].model_copy(update={"label": ", ".join(ids)})
        run = stated_by_labels(ids, (), request_texts)
        labelled[name] = held.sourced("stated", run) if run else held
    return labelled
