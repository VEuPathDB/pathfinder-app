"""WDK strategy materialization: a step tree as WDK steps."""

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import (
    DEFAULT_COMBINE_OPERATOR,
    ColocationParams,
    CombineOp,
    StrategyStepNode,
    flatten_tree,
    walk,
)
from veupathdb.errors import ValidationError
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    StrategyAPI,
    WDKSearchConfig,
    WDKStepTree,
    encode_params,
    get_strategy_api,
)

from pathfinder.domain.strategy.record_class_check import step_class_of
from pathfinder.services.strategies.record_classes import (
    fill_record_classes,
    tree_record_class_refusal,
    unclassed_step_failure,
)
from pathfinder.services.strategies.step_search import COLOCATION_SEARCH

logger = get_logger(__name__)


async def tree_classes(site_id: str, root: StrategyStepNode) -> dict[str, str]:
    refusal = await tree_record_class_refusal(site_id, root, {})
    if refusal is not None:
        raise ValidationError(title="The site cannot run this tree", detail=refusal)
    steps = flatten_tree(root)
    await fill_record_classes(site_id, steps)
    classes = {sid: step_class_of(steps, sid) for sid in steps}
    known = {sid: found for sid, found in classes.items() if found}
    unclassed = [steps[sid] for sid in steps if sid not in known]
    if unclassed:
        lost = unclassed_step_failure(unclassed[0].id, unclassed[0].search_name or "")
        raise ValidationError(title="A step has no record type", detail=lost.error)
    return known


async def materialize_step_tree(
    site_id: str, root: StrategyStepNode, made: list[int]
) -> WDKStepTree:
    return await materialize_classed_tree(
        site_id, root, await tree_classes(site_id, root), made
    )


async def materialize_classed_tree(
    site_id: str, root: StrategyStepNode, known: dict[str, str], made: list[int]
) -> WDKStepTree:
    api = get_strategy_api(site_id)
    created: dict[str, WDKStepTree] = {}
    for step in walk(root):
        slots: list[WDKStepTree | None] = [
            *(created[input_id] for input_id in step.input_ids()),
            None,
            None,
        ]
        created[step.id] = await _materialize_step(
            api, step, known[step.id], slots[0], slots[1]
        )
        made.append(created[step.id].step_id)
    return created[root.id]


async def _materialize_step(
    api: StrategyAPI,
    node: StrategyStepNode,
    record_type: str,
    primary_tree: WDKStepTree | None,
    secondary_tree: WDKStepTree | None,
) -> WDKStepTree:
    """Create the one WDK step this node describes, over its created inputs."""
    search_name = node.search_name
    wire_parameters = encode_params(node.parameters)
    display_name = node.display_name or search_name

    if primary_tree is not None and secondary_tree is not None:
        operator = node.operator or DEFAULT_COMBINE_OPERATOR
        if operator is CombineOp.COLOCATE:
            coloc = node.colocation_params
            if coloc is None:
                coloc = ColocationParams()
            # GenesBySpanLogic AnswerParams (span_a, span_b) are blanked
            # at creation; the returned step tree wires both inputs.
            step = await api.create_transform_step(
                NewStepSpec(
                    search_name=COLOCATION_SEARCH,
                    search_config=WDKSearchConfig(parameters=coloc.to_wdk_params()),
                    custom_name=display_name,
                ),
                input_step_id=primary_tree.step_id,
                record_type=record_type,
            )
        else:
            step = await api.create_combined_step(
                CombinedStepSpec(
                    primary_step_id=primary_tree.step_id,
                    secondary_step_id=secondary_tree.step_id,
                    boolean_operator=operator,
                    custom_name=display_name,
                ),
                record_type=record_type,
            )
        step_id = step.id
        return WDKStepTree(
            step_id=step_id, primary_input=primary_tree, secondary_input=secondary_tree
        )
    if primary_tree is not None:
        step = await api.create_transform_step(
            NewStepSpec(
                search_name=search_name,
                search_config=WDKSearchConfig(parameters=wire_parameters),
                custom_name=display_name,
            ),
            input_step_id=primary_tree.step_id,
            record_type=record_type,
        )
        step_id = step.id
        return WDKStepTree(step_id=step_id, primary_input=primary_tree)
    step = await api.create_step(
        NewStepSpec(
            search_name=search_name,
            search_config=WDKSearchConfig(parameters=wire_parameters),
            custom_name=display_name,
        ),
        record_type=record_type,
    )
    step_id = step.id
    return WDKStepTree(step_id=step_id)
