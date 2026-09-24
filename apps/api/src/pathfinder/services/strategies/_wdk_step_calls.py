"""The WDK calls that create or patch one step of a strategy."""

from collections.abc import Mapping

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import CombineOp, StrategyStep, wdk_search_name
from veupathdb.errors import ValidationError
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    StrategyAPI,
    WDKSearchConfig,
    encode_params,
)
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM

from pathfinder.domain.strategy.combine_naming import combine_name
from pathfinder.services.strategies.step_search import refuse_a_set_operation
from pathfinder.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)


def _refuse_an_empty_eda_analysis(str_params: Mapping[str, str]) -> None:
    """A step that names the analysis parameter and leaves it empty is refused.

    An empty analysis document states no subset, so the search answers every
    record of the study and the step filters nothing.
    """
    spec = str_params.get(EDA_ANALYSIS_SPEC_PARAM)
    if spec is None or spec.strip():
        return
    raise ValidationError(
        title="A step without an analysis",
        detail=(
            "This step carries an empty analysis, so it would answer every "
            "record of the study; it was not sent to the site. Export the step "
            "again from an analysis that holds a filter or a comparison."
        ),
    )


async def _push_leaf_step(
    api: StrategyAPI,
    search_name: str,
    str_params: dict[str, str],
    step: StrategyStep,
    record_type: str,
) -> int:
    """Push a leaf step to WDK. Returns the WDK step ID."""
    refuse_a_set_operation(step.id, search_name)
    _refuse_an_empty_eda_analysis(str_params)
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

    name = combine_name(step.display_name, step.search_name, parsed_op)
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
                custom_name=name,
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
            custom_name=name,
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
    refuse_a_set_operation(step.id, search_name)
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


async def _put_search_config(
    api: StrategyAPI,
    sync_state: WDKSyncState,
    step: StrategyStep,
    record_type: str,
) -> None:
    """Write the step's parameters and weight over the ones WDK holds."""
    refuse_a_set_operation(step.id, wdk_search_name(step))
    str_params: dict[str, str] = encode_params(step.parameters)
    _refuse_an_empty_eda_analysis(str_params)

    # A weight the graph does not hold stays whatever the site holds.
    config = WDKSearchConfig(parameters=str_params)
    if step.wdk_weight is not None:
        config = WDKSearchConfig(parameters=str_params, wdk_weight=step.wdk_weight)
    await api.update_step_search_config(
        step_id=sync_state.wdk_step_ids[step.id],
        search_config=config,
        record_type=record_type,
        search_name=wdk_search_name(step),
    )


async def _patch_name(
    api: StrategyAPI,
    sync_state: WDKSyncState,
    step: StrategyStep,
) -> None:
    """Write the name the step states."""
    await api.update_step_properties(
        step_id=sync_state.wdk_step_ids[step.id],
        spec=PatchStepSpec(custom_name=step.display_name),
    )
