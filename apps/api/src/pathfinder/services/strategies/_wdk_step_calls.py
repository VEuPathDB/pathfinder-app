"""The WDK calls that create or patch one step of a strategy."""

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy.graph_model import StrategyStep, wdk_search_name
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.wdk.strategy_api import StrategyAPI
from veupathdb.wdk.value_decoding import encode_params
from veupathdb.wdk.wdk_models import (
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    WDKSearchConfig,
)

from pathfinder.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)


async def _push_leaf_step(
    api: StrategyAPI,
    search_name: str,
    str_params: dict[str, str],
    step: StrategyStep,
    record_type: str,
) -> int:
    """Push a leaf step to WDK. Returns the WDK step ID."""
    wdk_result = await api.create_step(
        NewStepSpec(
            search_name=search_name,
            search_config=WDKSearchConfig(parameters=str_params),
            custom_name=step.display_name,
        ),
        record_type=record_type,
    )
    return wdk_result.id


async def _push_combine_step(
    api: StrategyAPI,
    sync_state: WDKSyncState,
    step: StrategyStep,
    record_type: str,
    parsed_op: CombineOp | None,
) -> int | None:
    """Push a combine step to WDK.

    Returns the WDK step ID or None if inputs are missing.
    """
    primary_wdk_id = (
        sync_state.wdk_step_ids.get(step.primary_input_id)
        if step.primary_input_id
        else None
    )
    secondary_wdk_id = (
        sync_state.wdk_step_ids.get(step.secondary_input_id)
        if step.secondary_input_id
        else None
    )
    if primary_wdk_id is None or secondary_wdk_id is None or parsed_op is None:
        logger.warning(
            "Cannot push combine step: missing WDK input IDs or operator",
            step_id=step.id,
            primary_wdk_id=primary_wdk_id,
            secondary_wdk_id=secondary_wdk_id,
            operator=str(parsed_op),
        )
        return None

    if parsed_op == CombineOp.COLOCATE:
        coloc = step.colocation_params
        if coloc is None:
            logger.warning("COLOCATE step missing colocation_params", step_id=step.id)
            return None
        # GenesBySpanLogic takes span_a and span_b as AnswerParams. The step
        # tree wires both inputs, so only the primary id is passed here.
        # The search lives under "transcript" for every record type.
        wdk_result = await api.create_transform_step(
            NewStepSpec(
                search_name="GenesBySpanLogic",
                search_config=WDKSearchConfig(parameters=coloc.to_wdk_params()),
                custom_name=step.display_name,
            ),
            input_step_id=primary_wdk_id,
            record_type="transcript",
        )
        return wdk_result.id

    wdk_result = await api.create_combined_step(
        CombinedStepSpec(
            primary_step_id=primary_wdk_id,
            secondary_step_id=secondary_wdk_id,
            boolean_operator=parsed_op,
            custom_name=step.display_name or None,
            wdk_weight=step.wdk_weight,
        ),
        record_type=record_type,
    )
    if step.expanded_strategy_id is not None:
        # The create-combined-step endpoint does not accept "expanded", so it
        # is set by a PATCH.
        await api.update_step_properties(
            wdk_result.id,
            spec=PatchStepSpec(
                expanded=True,
                expanded_name=step.expanded_name,
            ),
        )
    return wdk_result.id


async def _push_transform_step(
    api: StrategyAPI,
    sync_state: WDKSyncState,
    step: StrategyStep,
    search_name: str,
    str_params: dict[str, str],
    record_type: str,
) -> int | None:
    """Push a transform step to WDK.

    Returns the WDK step ID or None if input is missing.
    """
    input_wdk_id = (
        sync_state.wdk_step_ids.get(step.primary_input_id)
        if step.primary_input_id
        else None
    )
    if input_wdk_id is None:
        logger.warning(
            "Cannot push transform step: missing WDK input ID",
            step_id=step.id,
        )
        return None

    wdk_result = await api.create_transform_step(
        NewStepSpec(
            search_name=search_name,
            search_config=WDKSearchConfig(parameters=str_params),
            custom_name=step.display_name,
        ),
        input_wdk_id,
        record_type=record_type,
    )
    return wdk_result.id


async def _update_existing_step(
    api: StrategyAPI,
    sync_state: WDKSyncState,
    step: StrategyStep,
    record_type: str,
) -> None:
    """Update an existing WDK step's search-config (parameters + weight)."""
    wdk_step_id = sync_state.wdk_step_ids[step.id]
    kind = step.kind.value

    # The params of a combine step are structural and never change.
    if kind == "combine":
        return
    str_params: dict[str, str] = encode_params(step.parameters)

    await api.update_step_search_config(
        step_id=wdk_step_id,
        search_config=WDKSearchConfig(parameters=str_params),
        record_type=record_type,
        search_name=wdk_search_name(step),
    )


async def _patch_combine_metadata(
    api: StrategyAPI,
    sync_state: WDKSyncState,
    step: StrategyStep,
) -> None:
    # A WDK combine operator is a creation-time param. Only the display name
    # and the weight accept a PATCH.
    wdk_step_id = sync_state.wdk_step_ids[step.id]
    if step.display_name is None:
        return
    await api.update_step_properties(
        step_id=wdk_step_id,
        spec=PatchStepSpec(custom_name=step.display_name),
    )
