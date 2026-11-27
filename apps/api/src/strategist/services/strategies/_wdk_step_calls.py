"""The WDK calls that create or patch one step of a strategy."""

from collections.abc import Collection, Mapping
from typing import assert_never

from assistant_core.platform.logging import get_logger
from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters import ParamValue, wire_map
from veupathdb.domain.strategy import (
    CombineOp,
    StepFilter,
    StepKind,
    StepSettings,
    StrategyStep,
    settings_of,
    subtree_ids,
    wdk_search_name,
)
from veupathdb.errors import ValidationError, VEuPathDBError
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    PatchStepSpec,
    StrategyAPI,
    WDKFilterValue,
    WDKSearchConfig,
    WDKStep,
)
from veupathdb_mcp.catalog import EDA_ANALYSIS_SPEC_PARAM

from strategist.domain.strategy.build_outcome import StepPushFailure
from strategist.domain.strategy.combine_naming import combine_name
from strategist.services.strategies.step_push_planner import (
    CreateAction,
    PatchAction,
    RecreateAction,
)
from strategist.services.strategies.step_search import (
    COLOCATION_SEARCH,
    refuse_a_set_operation,
)
from strategist.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)

_SORTED_BY_WEIGHT = PatchStepSpec.model_validate(
    {
        "displayPreferences": {
            "sortColumns": [{"name": "wdk_weight", "direction": "DESC"}]
        }
    }
)


def _search_config(str_params: dict[str, str], step: StrategyStep) -> WDKSearchConfig:
    if step.wdk_weight is None:
        return WDKSearchConfig(parameters=str_params)
    return WDKSearchConfig(parameters=str_params, wdk_weight=step.wdk_weight)


def _held_settings(held: WDKStep) -> StepSettings:
    return StepSettings(
        filters=[
            StepFilter.model_validate(f.model_dump(by_alias=True, mode="json"))
            for f in held.search_config.filters
        ]
    )


def _on_the_wire(filters: list[StepFilter]) -> list[WDKFilterValue]:
    return [
        WDKFilterValue.model_validate(f.model_dump(by_alias=True, mode="json"))
        for f in filters
    ]


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
            search_config=_search_config(str_params, step),
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
        wdk_result = await api.create_transform_step(
            NewStepSpec(
                search_name=COLOCATION_SEARCH,
                search_config=_search_config(coloc.to_wdk_params(), step),
                custom_name=name,
            ),
            input_step_id=primary_wdk_id,
            record_type=record_type,
        )
    else:
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
    if step.expanded_name:
        # The create-combined-step call sends neither "expanded" nor
        # "expandedName", so both are set by a PATCH.
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
            search_config=_search_config(str_params, step),
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
    write: StepWrite,
) -> None:
    """Write the step's parameters, and its weight and filters when the turn moved
    them."""
    refuse_a_set_operation(step.id, wdk_search_name(step))
    str_params = wire_map(dict(write.parameters))
    _refuse_an_empty_eda_analysis(str_params)
    wdk_id = sync_state.wdk_step_ids[step.id]
    stated = settings_of(step)
    config = WDKSearchConfig(parameters=str_params)
    if "wdk_weight" in write.moved:
        config = config.model_copy(update={"wdk_weight": step.wdk_weight or 0})
    found = None
    if "filters" in write.moved:
        found = await api.find_step(wdk_id)
        filters = _held_settings(found).filters_to_put(write.before, stated)
        config = config.model_copy(update={"filters": _on_the_wire(filters)})
    await api.update_step_search_config(
        step_id=wdk_id,
        search_config=config,
        record_type=write.record_type,
        search_name=wdk_search_name(step),
        held=found,
    )


async def _patch_name(
    api: StrategyAPI,
    sync_state: WDKSyncState,
    step: StrategyStep,
) -> None:
    """Write the name the step states, and the name of the group it nests."""
    await api.update_step_properties(
        step_id=sync_state.wdk_step_ids[step.id],
        spec=PatchStepSpec(
            custom_name=step.display_name,
            expanded=True if step.expanded_name else None,
            expanded_name=step.expanded_name or None,
        ),
    )


async def _sort_a_ranking(
    api: StrategyAPI,
    sync_state: WDKSyncState,
    steps: Mapping[str, StrategyStep],
    root_id: str,
    pushed: Collection[str],
) -> None:
    if root_id not in sync_state.wdk_step_ids:
        return
    weighted = {
        step_id
        for step_id in subtree_ids(root_id, dict(steps))
        if steps[step_id].wdk_weight is not None
    }
    if weighted and not (weighted | {root_id}).isdisjoint(pushed):
        await api.update_step_properties(
            step_id=sync_state.wdk_step_ids[root_id], spec=_SORTED_BY_WEIGHT
        )


async def _new_step(
    api: StrategyAPI,
    sync_state: WDKSyncState,
    step: StrategyStep,
    record_type: str,
    parameters: Mapping[str, ParamValue],
) -> int | None:
    search_name = wdk_search_name(step)
    str_params = wire_map(dict(parameters))
    match step.kind:
        case StepKind.COMBINE:
            return await _push_combine_step(
                api, sync_state, step, record_type, step.operator
            )
        case StepKind.TRANSFORM:
            return await _push_transform_step(
                api, sync_state, step, search_name, str_params, record_type
            )
        case StepKind.SEARCH:
            return await _push_leaf_step(
                api, search_name, str_params, step, record_type
            )
        case _:
            assert_never(step.kind)


async def _put_the_stated_filters(
    api: StrategyAPI, sync_state: WDKSyncState, step: StrategyStep, record_type: str
) -> None:
    wdk_id = sync_state.wdk_step_ids[step.id]
    found = await api.find_step(wdk_id)
    held = _held_settings(found)
    wanted = held.filters_to_put(StepSettings(), settings_of(step))
    if wanted != held.filters:
        await api.update_step_search_config(
            step_id=wdk_id,
            search_config=WDKSearchConfig(
                parameters=dict(found.search_config.parameters),
                filters=_on_the_wire(wanted),
            ),
            record_type=record_type,
            search_name=found.search_name,
            held=found,
        )
    step.filters_wdk_added = held.filters_wdk_added(StepSettings())


def _failure(
    step: StrategyStep, error: str, status: int | None = None
) -> StepPushFailure:
    return StepPushFailure(
        step_id=step.id,
        search_name=wdk_search_name(step),
        error=error,
        wdk_status=status,
    )


async def pushed_step(
    api: StrategyAPI,
    sync_state: WDKSyncState,
    step: StrategyStep,
    record_type: str,
    parameters: Mapping[str, ParamValue],
) -> StepPushFailure | None:
    step.filters_wdk_added = None
    try:
        wdk_id = await _new_step(api, sync_state, step, record_type, parameters)
        if wdk_id is None:
            return _failure(step, "push returned no wdk step id")
        sync_state.wdk_step_ids[step.id] = wdk_id
    except VEuPathDBError as exc:
        return _failure(step, str(exc), exc.status)
    except OSError as exc:
        return _failure(step, str(exc))
    return await finished_step(api, sync_state, step, record_type)


async def finished_step(
    api: StrategyAPI, sync_state: WDKSyncState, step: StrategyStep, record_type: str
) -> StepPushFailure | None:
    try:
        await _put_the_stated_filters(api, sync_state, step, record_type)
    except VEuPathDBError as exc:
        return _failure(step, str(exc), exc.status)
    except OSError as exc:
        return _failure(step, str(exc))
    return None


class StepWrite(BaseModel):
    model_config = ConfigDict(frozen=True)

    record_type: str
    parameters: dict[str, ParamValue]
    before: StepSettings
    moved: frozenset[str]


async def written_step(
    api: StrategyAPI,
    sync_state: WDKSyncState,
    step: StrategyStep,
    action: CreateAction | PatchAction | RecreateAction,
    write: StepWrite,
) -> tuple[StepPushFailure | None, int | None]:
    record_type, parameters = write.record_type, write.parameters
    match action:
        case CreateAction():
            return await pushed_step(
                api, sync_state, step, record_type, parameters
            ), None
        case RecreateAction():
            replaced = sync_state.wdk_step_ids.get(step.id)
            failure = await pushed_step(api, sync_state, step, record_type, parameters)
            moved = sync_state.wdk_step_ids.get(step.id) != replaced
            return failure, (replaced if moved else None)
        case PatchAction():
            try:
                if action.search_config:
                    await _put_search_config(api, sync_state, step, write)
                if action.name:
                    await _patch_name(api, sync_state, step)
            except VEuPathDBError as exc:
                return _failure(step, str(exc), exc.status), None
            except OSError as exc:
                return _failure(step, str(exc)), None
            return None, None
        case _:
            assert_never(action)
