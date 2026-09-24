"""WDK strategy materialization: a step tree as WDK steps."""

from assistant_core.platform.logging import get_logger
from veupathdb.domain.strategy import (
    DEFAULT_COMBINE_OPERATOR,
    ColocationParams,
    CombineOp,
    StrategyStepNode,
    walk,
)
from veupathdb.wdk import (
    CombinedStepSpec,
    NewStepSpec,
    StrategyAPI,
    WDKSearchConfig,
    WDKStepTree,
    encode_params,
)

logger = get_logger(__name__)


async def _materialize_step_tree(
    api: StrategyAPI,
    node: StrategyStepNode,
    record_type: str,
) -> WDKStepTree:
    """Create the WDK steps of a :class:`StrategyStepNode` tree.

    ``walk`` yields every input before the step that consumes it, so
    each node finds its inputs already created.

    :param api: Strategy API instance.
    :param node: Strategy plan node.
    :param record_type: WDK record type for all steps.
    :returns: :class:`WDKStepTree` ready for strategy creation.
    """
    created: dict[str, WDKStepTree] = {}
    for step in walk(node):
        slots: list[WDKStepTree | None] = [
            *(created[input_id] for input_id in step.input_ids()),
            None,
            None,
        ]
        created[step.id] = await _materialize_step(
            api, step, record_type, slots[0], slots[1]
        )
    return created[node.id]


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
                    search_name="GenesBySpanLogic",
                    search_config=WDKSearchConfig(parameters=coloc.to_wdk_params()),
                    custom_name=display_name,
                ),
                input_step_id=primary_tree.step_id,
                record_type="transcript",
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
