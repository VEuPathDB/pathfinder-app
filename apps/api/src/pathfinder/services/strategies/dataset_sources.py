"""Turn the dataset source an edit carries into the dataset id the site reads."""

import re

import pydantic
from veupathdb.domain.parameters import InputDatasetValue, ParamValue
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.errors import ValidationError
from veupathdb.wdk import get_strategy_api
from veupathdb.wdk.wdk_models import WDKDatasetConfig

from pathfinder.domain.strategy.operations import (
    AddCombineOp,
    AddLeafOp,
    AddTransformOp,
    GraphOperation,
    ReplaceStrategyOp,
    ReplaceSubtreeOp,
    UpdateStepParamsOp,
)

_DATASET_ID = re.compile(r"^[1-9][0-9]*$")
_SOURCE = pydantic.TypeAdapter[WDKDatasetConfig](WDKDatasetConfig)


def dataset_source(name: str, value: ParamValue) -> WDKDatasetConfig | None:
    """The source a dataset value names, or None when it already names a dataset.

    A dataset parameter holds a positive integer on the site. Any other value
    must be the JSON of a dataset source, and a value that is neither fails.
    """
    match value:
        case InputDatasetValue(dataset_id=raw) if not _DATASET_ID.match(raw):
            try:
                return _SOURCE.validate_json(raw)
            except pydantic.ValidationError as exc:
                raise ValidationError(
                    title="The ID list is not one the site reads",
                    detail=(
                        f"Parameter {name!r} holds neither a dataset id nor an "
                        f"ID list: {exc.error_count()} problem(s) in {raw!r}."
                    ),
                ) from exc
        case _:
            return None


async def _saved(site_id: str, params: dict[str, ParamValue]) -> dict[str, ParamValue]:
    saved: dict[str, ParamValue] = {}
    for name, value in params.items():
        source = dataset_source(name, value)
        if source is None:
            saved[name] = value
            continue
        dataset_id = await get_strategy_api(site_id).create_dataset(source)
        saved[name] = InputDatasetValue(dataset_id=str(dataset_id))
    return saved


async def _saved_tree(site_id: str, node: StrategyStepNode) -> StrategyStepNode:
    primary = node.primary_input
    secondary = node.secondary_input
    return node.model_copy(
        update={
            "parameters": await _saved(site_id, node.parameters),
            "primary_input": None
            if primary is None
            else await _saved_tree(site_id, primary),
            "secondary_input": None
            if secondary is None
            else await _saved_tree(site_id, secondary),
        }
    )


async def save_dataset_sources(site_id: str, op: GraphOperation) -> GraphOperation:
    """The operation with every dataset source it carries saved on the site."""
    match op:
        case UpdateStepParamsOp():
            return op.model_copy(
                update={"parameters": await _saved(site_id, op.parameters)}
            )
        case AddLeafOp() | AddCombineOp() | AddTransformOp():
            return op.model_copy(update={"step": await _saved_tree(site_id, op.step)})
        case ReplaceSubtreeOp():
            return op.model_copy(
                update={"subtree": await _saved_tree(site_id, op.subtree)}
            )
        case ReplaceStrategyOp():
            return op.model_copy(update={"root": await _saved_tree(site_id, op.root)})
        case _:
            return op
