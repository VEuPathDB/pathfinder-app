"""WDK strategy materialization for experiments.

Creates, persists, and cleans up WDK strategies from experiment configs,
including step tree materialization for multi-step and import modes.
"""

from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONObject
from veupathdb.domain.strategy import (
    DEFAULT_COMBINE_OPERATOR,
    ColocationParams,
    CombineOp,
    StrategyStepNode,
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

from pathfinder.services.experiment.types import (
    ExperimentConfig,
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


async def _persist_experiment_strategy(
    config: ExperimentConfig,
    experiment_id: str,
    *,
    override_tree: StrategyStepNode | None = None,
) -> JSONObject:
    """Create a persisted WDK strategy for result exploration.

    Handles all experiment modes:

    * **single**: one search step.
    * **multi-step**: recursively materialise the ``step_tree``.
    * **import**: duplicate the step tree from an existing WDK strategy.

    :param config: Experiment configuration.
    :param experiment_id: Unique experiment identifier.
    :param override_tree: If provided, materialise this tree instead of the
        config's ``step_tree`` (used after tree optimisation).
    :returns: Dict with ``strategy_id`` and ``step_id``.
    """
    api = get_strategy_api(config.site_id)
    mode = config.mode or "single"

    if mode == "import" and config.source_strategy_id and override_tree is None:
        return await _persist_import_strategy(api, config, experiment_id)

    effective_tree = override_tree or config.step_tree
    if mode in ("multi-step", "import") and effective_tree is not None:
        root_tree = await _materialize_step_tree(
            api, effective_tree, config.record_type
        )
    else:
        step_payload = await api.create_step(
            NewStepSpec(
                search_name=config.search_name,
                search_config=WDKSearchConfig(
                    parameters=encode_params(config.parameters)
                ),
                custom_name=f"Experiment: {config.name}",
            ),
            record_type=config.record_type,
        )
        step_id = step_payload.id
        root_tree = WDKStepTree(step_id=step_id)

    created = await api.create_strategy(
        step_tree=root_tree,
        name=f"exp:{experiment_id}",
        description=f"Persisted strategy for experiment {config.name}",
        is_internal=True,
    )
    strategy_id = created.id

    logger.info(
        "Persisted WDK strategy for experiment",
        experiment_id=experiment_id,
        strategy_id=strategy_id,
        step_id=root_tree.step_id,
    )
    return {"strategy_id": strategy_id, "step_id": root_tree.step_id}


async def _persist_import_strategy(
    api: StrategyAPI,
    config: ExperimentConfig,
    experiment_id: str,
) -> JSONObject:
    """Import an existing WDK strategy by duplicating its step tree.

    Uses the WDK ``duplicated-step-tree`` endpoint to copy the source
    strategy's step tree into a new set of unattached steps.

    :param api: Strategy API instance.
    :param config: Experiment configuration (must have ``source_strategy_id``).
    :param experiment_id: Unique experiment identifier.
    :returns: Dict with ``strategy_id`` and ``step_id``.
    """
    if not config.source_strategy_id:
        msg = "source_strategy_id is required for import mode"
        raise ValidationError(detail=msg)
    source_id = int(config.source_strategy_id)

    dup_tree = await api.get_duplicated_step_tree(source_id)

    # The duplicated tree already carries real WDK step ids.
    created = await api.create_strategy(
        step_tree=dup_tree,
        name=f"exp:{experiment_id}",
        description=f"Imported strategy for experiment {config.name}",
        is_internal=True,
    )
    strategy_id = created.id

    logger.info(
        "Persisted imported WDK strategy for experiment",
        experiment_id=experiment_id,
        strategy_id=strategy_id,
        step_id=dup_tree.step_id,
    )
    return {"strategy_id": strategy_id, "step_id": dup_tree.step_id}
