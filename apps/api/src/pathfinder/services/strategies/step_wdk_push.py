"""WDK push logic for step creation.

A failed push leaves the step in the local graph for the sync service to
reconcile later.
"""

from typing import assert_never

from assistant_core.platform.logging import get_logger
from pydantic import BaseModel, ConfigDict
from veupathdb.domain.parameters.values import ParamValue
from veupathdb.domain.search import SearchContext
from veupathdb.domain.strategy.graph_model import (
    StepKind,
    StepStatus,
    StrategyStep,
    record_class_of,
    runs_a_wdk_search,
    step_status,
    wdk_search_name,
)
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.session import StrategyGraph
from veupathdb.domain.strategy.validation import StepValidation
from veupathdb.errors import ValidationError, VEuPathDBError
from veupathdb.wdk.factory import get_strategy_api
from veupathdb.wdk.value_decoding import encode_params
from veupathdb_mcp.catalog.param_validation import (
    ValidationCallbacks,
    validate_parameters,
)
from veupathdb_mcp.catalog.searches import assign_step_record_classes
from veupathdb_mcp.catalog.validation_callbacks import make_validation_callbacks

from pathfinder.platform.errors import AppError
from pathfinder.services.strategies._wdk_step_calls import (
    _patch_combine_metadata,
    _push_combine_step,
    _push_leaf_step,
    _push_transform_step,
    _update_existing_step,
)
from pathfinder.services.strategies.step_push_planner import (
    CreateAction,
    PatchAction,
    RecreateAction,
    SkipAction,
    StepPushPlan,
)
from pathfinder.services.strategies.sync_state import WDKSyncState


class PushOutcome(BaseModel):
    """Step ids of a push plan, split by result and kept in plan order."""

    model_config = ConfigDict(frozen=True)
    succeeded: list[str]
    failed: list[str]

    @property
    def partial(self) -> bool:
        return len(self.failed) > 0


logger = get_logger(__name__)


async def push_step_to_wdk(
    *,
    sync_state: WDKSyncState,
    step: StrategyStep,
    site_id: str,
    record_type: str,
    search_name: str,
    parameters: dict[str, ParamValue],
) -> tuple[int | None, StepValidation | None, str | None]:
    """Push a newly created step to WDK and store its id on sync_state.

    A rejected push returns the reason in ``push_error`` and does not raise.
    """
    parsed_op: CombineOp | None = step.operator
    wdk_step_id: int | None = None
    wdk_validation: StepValidation | None = None
    push_error: str | None = None
    str_params: dict[str, str] = encode_params(parameters)
    try:
        api = get_strategy_api(site_id)
        is_binary = step.kind is StepKind.COMBINE
        is_transform = step.kind is StepKind.TRANSFORM

        if is_binary:
            wdk_step_id = await _push_combine_step(
                api, sync_state, step, record_type, parsed_op
            )
        elif is_transform:
            wdk_step_id = await _push_transform_step(
                api, sync_state, step, search_name, str_params, record_type
            )
        else:
            wdk_step_id = await _push_leaf_step(
                api, search_name, str_params, step, record_type
            )

        if wdk_step_id is not None:
            sync_state.wdk_step_ids[step.id] = wdk_step_id
            try:
                wdk_step = await api.find_step(wdk_step_id)
                wdk_validation = wdk_step.validation
            except AppError, VEuPathDBError, OSError:
                wdk_validation = None

    except (AppError, VEuPathDBError, OSError) as exc:
        push_error = str(exc)
        logger.warning(
            "WDK step push failed (non-fatal)",
            step_id=step.id,
            search_name=search_name,
            error=push_error,
        )

    return wdk_step_id, wdk_validation, push_error


async def _execute_patch(
    sync_state: WDKSyncState,
    site_id: str,
    step: StrategyStep,
    record_type: str,
) -> str | None:
    api = get_strategy_api(site_id)
    try:
        if step.kind.value == "combine":
            await _patch_combine_metadata(api, sync_state, step)
        else:
            await _update_existing_step(api, sync_state, step, record_type)
    except (AppError, VEuPathDBError, OSError) as exc:
        msg = str(exc)
        sync_state.wdk_push_errors[step.id] = msg
        return msg
    return None


async def _execute_create(
    sync_state: WDKSyncState,
    site_id: str,
    step: StrategyStep,
    record_type: str,
) -> str | None:
    wdk_step_id, _validation, push_error = await push_step_to_wdk(
        sync_state=sync_state,
        step=step,
        site_id=site_id,
        record_type=record_type,
        search_name=wdk_search_name(step),
        parameters=step.parameters,
    )
    if wdk_step_id is None:
        if push_error:
            sync_state.wdk_push_errors[step.id] = push_error
        return push_error or "push returned no wdk step id"
    return None


async def _execute_recreate(
    sync_state: WDKSyncState,
    site_id: str,
    step: StrategyStep,
    record_type: str,
) -> str | None:
    sync_state.wdk_step_ids.pop(step.id, None)
    return await _execute_create(sync_state, site_id, step, record_type)


def defer_draft_steps(
    plan: list[StepPushPlan],
    *,
    steps_by_id: dict[str, StrategyStep],
    open_param_step_ids: set[str],
    existing_wdk_ids: dict[str, int],
) -> list[StepPushPlan]:
    """Replace the action of each step that is not ready with a skip.

    A step that is already in WDK is never deferred, because a draft is left
    out of the built strategy.
    """
    deferred: list[StepPushPlan] = []
    for entry in plan:
        step = steps_by_id.get(entry.step_id)
        already_live = entry.step_id in existing_wdk_ids
        status = (
            step_status(
                step,
                wdk_step_id=existing_wdk_ids.get(entry.step_id),
                validation=None,
                has_open_params=entry.step_id in open_param_step_ids,
            )
            if step is not None
            else StepStatus.BUILT
        )
        is_draft_to_defer = (
            step is not None
            and not status.is_pushable
            and not already_live
            and not isinstance(entry.action, SkipAction)
        )
        if is_draft_to_defer:
            deferred.append(
                StepPushPlan(
                    step_id=entry.step_id,
                    action=SkipAction(),
                    reason="draft: not ready to build yet",
                )
            )
            continue
        deferred.append(entry)
    return deferred


async def _validate_plan_params(
    plan: list[StepPushPlan],
    steps_by_id: dict[str, StrategyStep],
    site_id: str,
    strategy_class: str,
    existing_wdk_ids: dict[str, int],
) -> set[str]:
    """Canonicalize the params of each pushable step in place.

    Validation resolves the record class WDK lists the step's search under, and
    the step keeps it. An incomplete step that is already in WDK raises instead
    of being reported, because a draft is left out of the built strategy.
    """
    callbacks: ValidationCallbacks = make_validation_callbacks(site_id)

    async def _listed_under(search_name: str) -> str | None:
        return await callbacks.resolve_record_type_for_search(None, search_name)

    await assign_step_record_classes(steps_by_id, _listed_under)
    incomplete: set[str] = set()
    for entry in plan:
        step = steps_by_id.get(entry.step_id)
        if step is None or isinstance(entry.action, SkipAction):
            continue
        if not runs_a_wdk_search(step):
            continue
        try:
            validated = await validate_parameters(
                SearchContext(
                    site_id=site_id,
                    record_type=record_class_of(
                        entry.step_id, steps_by_id, fallback=strategy_class
                    ),
                    search_name=wdk_search_name(step),
                ),
                parameters=dict(step.parameters),
                callbacks=callbacks,
            )
        except ValidationError:
            if entry.step_id in existing_wdk_ids:
                raise
            incomplete.add(entry.step_id)
        else:
            step.parameters = validated.params
            if validated.record_class:
                step.record_class = validated.record_class
    return incomplete


async def push_steps_with_plan(
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    site_id: str,
    plan: list[StepPushPlan],
) -> PushOutcome:
    """Execute a push plan.

    A failed step does not stop the plan. A combine whose input failed has no
    input id, so it also fails.
    """
    if graph.primary_root_id() is None:
        return PushOutcome(succeeded=[], failed=[])

    steps_by_id: dict[str, StrategyStep] = dict(graph.steps)
    strategy_class = graph.record_type or "transcript"

    incomplete = await _validate_plan_params(
        plan, steps_by_id, site_id, strategy_class, sync_state.wdk_step_ids
    )
    plan = defer_draft_steps(
        plan,
        steps_by_id=steps_by_id,
        open_param_step_ids=incomplete,
        existing_wdk_ids=sync_state.wdk_step_ids,
    )

    succeeded: list[str] = []
    failed: list[str] = []

    for entry in plan:
        step = steps_by_id.get(entry.step_id)
        if step is None:
            continue
        action = entry.action
        if isinstance(action, SkipAction):
            continue
        record_type = record_class_of(step.id, steps_by_id, fallback=strategy_class)
        if isinstance(action, PatchAction):
            err = await _execute_patch(sync_state, site_id, step, record_type)
        elif isinstance(action, CreateAction):
            err = await _execute_create(sync_state, site_id, step, record_type)
        elif isinstance(action, RecreateAction):
            err = await _execute_recreate(sync_state, site_id, step, record_type)
        else:
            assert_never(action)
        if err is None:
            succeeded.append(step.id)
        else:
            failed.append(step.id)

    return PushOutcome(succeeded=succeeded, failed=failed)
