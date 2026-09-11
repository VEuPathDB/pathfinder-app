"""Control evaluation logic: run trees/steps against control sets and extract metrics."""

from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONArray, JSONObject
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.wdk.factory import get_strategy_api
from veupathdb.wdk.strategy_api import StrategyAPI
from veupathdb.wdk.wdk_models import (
    CombinedStepSpec,
    NewStepSpec,
    WDKDatasetConfigIdList,
    WDKDatasetIdListContent,
    WDKSearchConfig,
    WDKStepTree,
)
from veupathdb_mcp.controls import (
    ControlsContext,
    ControlSetData,
    ControlTargetData,
    ControlTestResult,
    delete_temp_strategy,
    resolve_controls_param_type,
    summarize_intersection,
)
from veupathdb_mcp.wdk import extract_record_ids

from pathfinder.services.experiment.materialization import (
    _materialize_step_tree,
)

logger = get_logger(__name__)

# Skip fetching individual intersection IDs when the control set is large
# to avoid expensive WDK answer-page requests; counts alone suffice for metrics.
_MAX_CONTROL_IDS_FOR_ANSWER = 500


async def _eval_control_set(
    api: StrategyAPI,
    ctx: ControlsContext,
    tree: StrategyStepNode,
    control_ids: list[str],
    label: str,
) -> JSONObject:
    """Materialise the tree, intersect with one control set, clean up."""
    root_tree = await _materialize_step_tree(api, tree, ctx.record_type)

    param_type = await resolve_controls_param_type(
        api,
        ctx.record_type,
        ctx.controls_search_name,
        ctx.controls_param_name,
    )

    controls_params: JSONObject = {}
    if param_type == "input-dataset":
        config_ds = WDKDatasetConfigIdList(
            source_type="idList",
            source_content=WDKDatasetIdListContent(ids=control_ids),
        )
        dataset_id = await api.create_dataset(config_ds)
        controls_params[ctx.controls_param_name] = str(dataset_id)
    else:
        controls_params[ctx.controls_param_name] = "\n".join(control_ids)

    controls_step = await api.create_step(
        NewStepSpec(
            search_name=ctx.controls_search_name,
            search_config=WDKSearchConfig(
                parameters={
                    k: str(v) for k, v in controls_params.items() if v is not None
                },
            ),
            custom_name=f"Controls ({label})",
        ),
        record_type=ctx.record_type,
    )
    controls_step_id = controls_step.id

    combined = await api.create_combined_step(
        CombinedStepSpec(
            primary_step_id=root_tree.step_id,
            secondary_step_id=controls_step_id,
            boolean_operator=CombineOp.INTERSECT,
            custom_name=f"Tree \u2229 {label}",
        ),
        record_type=ctx.record_type,
    )
    combined_step_id = combined.id

    full_tree = WDKStepTree(
        step_id=combined_step_id,
        primary_input=root_tree,
        secondary_input=WDKStepTree(step_id=controls_step_id),
    )
    created = await api.create_strategy(
        step_tree=full_tree,
        name="Pathfinder tree eval",
        is_internal=True,
    )
    strategy_id = created.id

    try:
        target_total = await api.get_step_count(root_tree.step_id)
        intersection_total = await api.get_step_count(combined_step_id)

        intersection_ids: list[str] | None = None
        if len(control_ids) <= _MAX_CONTROL_IDS_FOR_ANSWER:
            answer = await api.get_step_answer(
                combined_step_id,
                pagination={
                    "offset": 0,
                    "numRecords": min(len(control_ids), _MAX_CONTROL_IDS_FOR_ANSWER),
                },
            )
            intersection_ids = extract_record_ids(answer.records)

        ids_list: JSONArray | None = (
            list(intersection_ids) if intersection_ids is not None else None
        )
        ids_sample: JSONArray = list(intersection_ids[:50] if intersection_ids else ())
        return {
            "controlsCount": len(control_ids),
            "intersectionCount": intersection_total,
            "intersectionIds": ids_list,
            "intersectionIdsSample": ids_sample,
            "targetStepId": root_tree.step_id,
            "targetEstimatedSize": target_total,
        }
    finally:
        await delete_temp_strategy(api, strategy_id)


async def run_controls_against_tree(
    ctx: ControlsContext,
    tree: StrategyStepNode,
) -> ControlTestResult:
    """Materialise a ``StrategyStepNode`` tree, intersect with controls, return metrics.

    Creates a temporary WDK strategy containing the full tree, adds an
    intersection step with each control set on top of the root, queries the
    result counts, then deletes everything.

    Returns a :class:`ControlTestResult` so :func:`metrics_from_control_result`
    can consume it directly.
    """
    api = get_strategy_api(ctx.site_id)

    pos = [s.strip() for s in ctx.positive_controls if s.strip()]
    neg = [s.strip() for s in ctx.negative_controls if s.strip()]

    target = ControlTargetData(search_name="__tree__")
    result = ControlTestResult(
        site_id=ctx.site_id,
        record_type=ctx.record_type,
        target=target,
    )

    if pos:
        pos_payload = await _eval_control_set(api, ctx, tree, pos, "positive")
        pos_data = ControlSetData.model_validate(pos_payload)

        found = summarize_intersection(pos_payload)
        recovered = found.found_ids
        missing = [x for x in pos if x not in recovered] if found.ids_were_read else []

        target.estimated_size = pos_data.target_estimated_size
        pos_data.missing_ids_sample = missing[:50]
        pos_data.recall = found.intersection_count / len(pos) if pos else None
        result.positive = pos_data

    if neg:
        neg_payload = await _eval_control_set(api, ctx, tree, neg, "negative")
        neg_data = ControlSetData.model_validate(neg_payload)

        if target.estimated_size is None:
            target.estimated_size = neg_data.target_estimated_size

        hits = summarize_intersection(neg_payload)
        neg_data.unexpected_hits_sample = sorted(hits.found_ids)[:50]
        neg_data.false_positive_rate = (
            hits.intersection_count / len(neg) if neg else None
        )
        result.negative = neg_data

    return result
