from dataclasses import dataclass
from typing import Literal, Protocol

from assistant_core.platform.logging import get_logger
from veupathdb.domain.parameters import InputDatasetValue
from veupathdb.domain.strategy import (
    StrategyStep,
    StrategyStepNode,
    walk,
)
from veupathdb.errors import VEuPathDBError
from veupathdb.wdk import (
    StrategyAPI,
    WDKDatasetConfigIdList,
    WDKDatasetIdListContent,
    WDKStrategyDetails,
)

from strategist.domain.strategy.validate import validate_strategy
from strategist.platform.errors import StrategyCompilationError
from strategist.services.strategies.organism_params import (
    tree_dataset_organisms,
    tree_organism_parameters,
    tree_taxa,
)
from strategist.services.strategies.result_list import result_list_url
from strategist.services.strategies.sync import (
    SyncResult,
    TreeNotHeldError,
    build_step_tree_from_graph,
    step_tree_is_current,
)
from strategist.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)

type StrategyRole = Literal["thread", "saved", "internal"]


@dataclass(frozen=True)
class StrategyLabels:
    name: str
    description: str


def _lagging(held: str | None, wanted: str) -> str | None:
    return wanted if held is not None and held != wanted else None


async def put_the_strategy_labels(
    api: StrategyAPI, sync_state: WDKSyncState, labels: StrategyLabels
) -> None:
    if sync_state.wdk_strategy_id is None:
        return
    name = _lagging(sync_state.wdk_strategy_name, labels.name)
    description = _lagging(sync_state.wdk_strategy_description, labels.description)
    if name is None and description is None:
        return
    try:
        await api.update_strategy(
            sync_state.wdk_strategy_id, name=name, description=description
        )
    except VEuPathDBError as exc:
        logger.warning(
            "WDK did not take the strategy's labels",
            wdk_strategy_id=sync_state.wdk_strategy_id,
            error=str(exc),
        )
        return
    if name is not None:
        sync_state.wdk_strategy_name = name
    if description is not None:
        sync_state.wdk_strategy_description = description


@dataclass(frozen=True)
class WrittenTree:
    strategy_id: int
    root_step_id: int
    created: bool


class TreeTarget(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def description(self) -> str: ...
    @property
    def role(self) -> StrategyRole: ...


async def put_the_tree(
    api: StrategyAPI,
    site_id: str,
    root: StrategyStepNode,
    record_type: str,
    sync_state: WDKSyncState,
    target: TreeTarget,
) -> WrittenTree | None:
    await _validate_the_tree(site_id, root, record_type, sync_state)
    labels = StrategyLabels(name=target.name, description=target.description)
    return await _write_the_tree(api, root, sync_state, labels, target.role)


async def _validate_the_tree(
    site_id: str, root: StrategyStepNode, record_type: str, sync_state: WDKSyncState
) -> None:
    sync_state.organism_params = await tree_organism_parameters(site_id, root)
    datasets = await tree_dataset_organisms(site_id, root, sync_state.organism_params)
    taxa = await tree_taxa(site_id, root, sync_state.organism_params, datasets)
    result = validate_strategy(
        root, record_type, sync_state.organism_params, datasets, taxa=taxa
    )
    if not result.valid:
        errors = [{"path": e.path, "message": e.message} for e in result.errors]
        msg = f"Strategy validation failed: {errors}"
        raise StrategyCompilationError(msg)


async def _write_the_tree(
    api: StrategyAPI,
    root: StrategyStepNode,
    sync_state: WDKSyncState,
    labels: StrategyLabels,
    role: StrategyRole,
) -> WrittenTree | None:
    if step_tree_is_current(root, sync_state):
        await put_the_strategy_labels(api, sync_state, labels)
        return None
    step_tree = build_step_tree_from_graph(root, sync_state.wdk_step_ids)
    strategy_id = sync_state.wdk_strategy_id
    if strategy_id is None:
        made = await api.create_strategy(
            step_tree,
            labels.name,
            description=labels.description,
            is_internal=role == "internal",
        )
        strategy_id = made.id
    else:
        held = await api.update_strategy(
            strategy_id=strategy_id,
            step_tree=step_tree,
            name=labels.name,
            description=labels.description,
        )
        if held.step_tree != step_tree:
            raise TreeNotHeldError(step_tree, held.step_tree)
    created = sync_state.wdk_strategy_id is None
    sync_state.wdk_strategy_id = strategy_id
    sync_state.wdk_strategy_name = labels.name
    sync_state.wdk_strategy_description = labels.description
    sync_state.wdk_step_tree = step_tree
    return WrittenTree(strategy_id, step_tree.step_id, created)


async def delete_what_the_tree_dropped(
    api: StrategyAPI, steps: dict[str, StrategyStep], sync_state: WDKSyncState
) -> None:
    replaced = list(sync_state.replaced_wdk_step_ids)
    dropped = {
        local: wdk
        for local, wdk in sync_state.wdk_step_ids.items()
        if local not in steps
    }
    for local in {*sync_state.step_counts, *sync_state.step_validations} - steps.keys():
        sync_state.step_counts.pop(local, None)
        sync_state.step_validations.pop(local, None)
    if not dropped and not replaced:
        return
    leftover = set(await api.delete_orphaned_steps([*dropped.values(), *replaced]))
    sync_state.replaced_wdk_step_ids = [i for i in replaced if i in leftover]
    for local, wdk in dropped.items():
        if wdk not in leftover:
            sync_state.wdk_step_ids.pop(local, None)
            sync_state.wdk_push_errors.pop(local, None)
    if leftover:
        logger.warning(
            "Some orphaned WDK steps could not be deleted", step_ids=sorted(leftover)
        )


async def read_the_strategy(
    api: StrategyAPI, sync_state: WDKSyncState
) -> WDKStrategyDetails | None:
    if sync_state.wdk_strategy_id is None:
        return None
    try:
        live = await api.get_strategy(sync_state.wdk_strategy_id)
    except (VEuPathDBError, OSError) as exc:
        logger.warning("Strategy count lookup failed", error=str(exc))
        return None
    local = {wdk: sid for sid, wdk in sync_state.wdk_step_ids.items()}
    counts: dict[str, int | None] = {}
    sync_state.step_validations = {}
    for wdk_id, step in live.steps.items():
        sid = local.get(int(wdk_id)) if wdk_id.isdigit() else None
        if sid is None:
            continue
        counts[sid] = step.estimated_size
        if step.validation is not None:
            sync_state.step_validations[sid] = step.validation
    sync_state.step_counts = counts
    return live


def sync_result(
    site_id: str, root: StrategyStepNode, sync_state: WDKSyncState, written: WrittenTree
) -> SyncResult:
    counts = dict(sync_state.step_counts)
    return SyncResult(
        wdk_strategy_id=written.strategy_id,
        wdk_url=result_list_url(site_id, written.strategy_id, written.root_step_id),
        root_step_id=written.root_step_id,
        counts=counts,
        root_count=counts.get(root.id),
        zero_step_ids=sorted(sid for sid, c in counts.items() if c == 0),
        step_count=len(walk(root)),
        created_wdk_strategy=written.created,
    )


async def provision_the_datasets(
    api: StrategyAPI, steps: dict[str, StrategyStep], datasets: dict[str, list[str]]
) -> None:
    for param_name, gene_ids in datasets.items():
        config = WDKDatasetConfigIdList(
            source_type="idList",
            source_content=WDKDatasetIdListContent(ids=gene_ids),
        )
        made = await api.create_dataset(config)
        logger.info(
            "Created a dataset for a tree",
            param_name=param_name,
            gene_count=len(gene_ids),
            dataset_id=made,
        )
        for step in steps.values():
            if param_name in step.parameters:
                step.parameters[param_name] = InputDatasetValue(dataset_id=str(made))


async def undo_the_tree(api: StrategyAPI, sync_state: WDKSyncState) -> None:
    if sync_state.wdk_strategy_id is not None:
        await api.delete_strategy(sync_state.wdk_strategy_id)
    else:
        await api.delete_orphaned_steps(list(sync_state.wdk_step_ids.values()))
    sync_state.wdk_strategy_id = None
    sync_state.wdk_step_tree = None
    sync_state.wdk_step_ids = {}
