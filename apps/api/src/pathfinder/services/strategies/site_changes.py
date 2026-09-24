"""The values and the shape a strategy holds on the site, taken onto its graph.

The researcher edits the strategy on VEuPathDB as well as here. The graph owns
what the strategy is, so it takes what the site moved before anything is
planned against it or counted on it. Both sides are trees: a stored value is
compared with the site's wire value and with its decoded form, never with a
spec value.
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from assistant_core.platform.db import DBSessionFactory
from assistant_core.platform.logging import get_logger
from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    CombineOp,
    StepKind,
    StrategyAst,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
    rebuild_tree,
    subtree_ids,
    walk,
)
from veupathdb.errors import DataParsingError, VEuPathDBError
from veupathdb.wdk import (
    WDKSearchConfig,
    WDKStrategyDetails,
    encode_params,
    get_strategy_api,
)
from veupathdb_mcp.wdk import build_snapshot_from_wdk, canonicalize_synced_parameters

from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.eda.analysis_kinds import read_the_unread_kinds
from pathfinder.services.strategies.context import StrategyMutationContext
from pathfinder.services.strategies.live_counts import read_the_live_strategy
from pathfinder.services.strategies.persist import (
    persist_strategy_ast_to_conversation,
)
from pathfinder.services.strategies.session_factory import stored_strategy_session
from pathfinder.services.strategies.sync_state import WDKSyncState, ensure_sync_state
from pathfinder.services.strategies.write_lock import strategy_write_lock

logger = get_logger(__name__)

__all__ = [
    "SiteEdits",
    "read_the_site_into_the_thread",
    "take_the_sites_edits",
    "take_what_the_site_holds",
]

Wire = Mapping[str, str]


class SiteEdits(BaseModel):
    """What the graph took from the site."""

    model_config = ConfigDict(frozen=True)

    valued: list[str] = Field(default_factory=list)
    """The steps whose values the site moved."""
    reshaped: bool = False
    """Whether the graph took the site's tree."""

    @property
    def moved(self) -> bool:
        return bool(self.valued) or self.reshaped


class _SiteTree(BaseModel):
    """The site's tree keyed by WDK step id, with each step's wire values."""

    model_config = ConfigDict(frozen=True)

    ast: StrategyAst
    wire: dict[str, dict[str, str]]


async def take_the_sites_edits(
    *, graph: StrategyGraph, sync_state: WDKSyncState, site_id: str
) -> SiteEdits:
    """Read the strategy on the site and take what it moved.

    A strategy the site does not hold, or a read that fails, takes nothing.
    """
    live = await read_the_live_strategy(sync_state, site_id)
    if live is None:
        return SiteEdits()
    return await take_what_the_site_holds(
        graph=graph, sync_state=sync_state, site_id=site_id, live=live
    )


async def read_the_site_into_the_thread(
    *,
    session: StrategySession,
    conversation_id: UUID,
    db_session_factory: DBSessionFactory,
) -> WDKStrategyDetails | None:
    """Store what the site moved on the thread's strategy, and hand ``session`` it.

    The stored graph is read again under the thread's write lock, so the site's
    edit lands on the tree the last writer left. A thread with no steps has
    nothing the site can move, so its read takes no lock. The answer is the
    site's strategy, or None when the site does not hold one or does not answer.
    """
    held = session.sync_state
    if held is None or held.wdk_strategy_id is None or not held.wdk_step_ids:
        return None
    graph = session.get_graph(None)
    if graph is None or not graph.steps:
        return await read_the_live_strategy(held, session.site_id)
    async with strategy_write_lock(conversation_id, db_session_factory) as locked:
        stored = await stored_strategy_session(locked, conversation_id, session.site_id)
        stored_graph = None if stored is None else stored.get_graph(None)
        if stored is None or stored_graph is None:
            return None
        sync_state = ensure_sync_state(stored)
        live = await read_the_live_strategy(sync_state, session.site_id)
        if live is None:
            return None
        edits = await take_what_the_site_holds(
            graph=stored_graph,
            sync_state=sync_state,
            site_id=session.site_id,
            live=live,
        )
        if not edits.moved:
            return live
        await persist_strategy_ast_to_conversation(
            deps=StrategyMutationContext(
                site_id=session.site_id,
                strategy_session=stored,
                conversation_id=conversation_id,
                locked_session=locked,
            ),
            graph=stored_graph,
            sync_result=None,
        )
    session.graph = stored_graph
    session.sync_state = sync_state
    return live


async def take_what_the_site_holds(
    *,
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    site_id: str,
    live: WDKStrategyDetails,
) -> SiteEdits:
    """Write onto the graph the values and the shape ``live`` moved."""
    local_of = {wdk_id: local for local, wdk_id in sync_state.wdk_step_ids.items()}
    tree = _the_sites_tree(live)
    valued = await _take_the_sites_values(graph, local_of, live, tree, site_id)
    reshaped = tree is not None and await _take_the_sites_shape(
        graph, sync_state, local_of, live, tree, site_id
    )
    if valued or reshaped:
        logger.info(
            "Took the site's edits onto the graph",
            strategy_id=live.strategy_id,
            valued=valued,
            reshaped=reshaped,
        )
    return SiteEdits(valued=valued, reshaped=reshaped)


def _the_sites_tree(live: WDKStrategyDetails) -> _SiteTree | None:
    """The site's tree, or None when a step on it is not one the snapshot reads."""
    try:
        ast, wire = build_snapshot_from_wdk(live)
    except DataParsingError, ValueError:
        logger.warning("The site's tree is not readable", strategy_id=live.strategy_id)
        return None
    return _SiteTree(ast=ast, wire=wire)


def _held_step(
    graph: StrategyGraph, local_of: Mapping[int, str], wdk_key: str
) -> StrategyStep | None:
    local = local_of.get(int(wdk_key)) if wdk_key.isdigit() else None
    return None if local is None else graph.steps.get(local)


async def _take_the_sites_values(
    graph: StrategyGraph,
    local_of: Mapping[int, str],
    live: WDKStrategyDetails,
    tree: _SiteTree | None,
    site_id: str,
) -> list[str]:
    operators = (
        {}
        if tree is None
        else {node.id: node.operator for node in walk(tree.ast.root) if node.operator}
    )
    moved: list[str] = []
    for wdk_key, wdk_step in live.steps.items():
        step = _held_step(graph, local_of, wdk_key)
        if step is None:
            continue
        if step.kind is StepKind.COMBINE:
            taken = _take_the_operator(step, operators.get(wdk_key))
        else:
            taken = await _take_the_parameters(
                step,
                wdk_step.search_name,
                wdk_step.search_config.parameters,
                record_type=step.record_class or graph.record_type or "",
                site_id=site_id,
            )
        weighed = _take_the_weight(step, wdk_step.search_config)
        if taken or weighed:
            moved.append(step.id)
    return moved


def _take_the_weight(step: StrategyStep, config: WDKSearchConfig) -> bool:
    """A graph that holds no weight leaves the weight to the site."""
    if step.wdk_weight is None or "wdk_weight" not in config.model_fields_set:
        return False
    if config.wdk_weight == step.wdk_weight:
        return False
    step.wdk_weight = config.wdk_weight
    return True


def _take_the_operator(step: StrategyStep, operator: CombineOp | None) -> bool:
    """A colocation is not a set operation, so it keeps its own operator."""
    if operator is None or step.operator in (None, CombineOp.COLOCATE):
        return False
    if operator == step.operator:
        return False
    step.operator = operator
    return True


async def _take_the_parameters(
    step: StrategyStep,
    search_name: str,
    wire: Wire,
    *,
    record_type: str,
    site_id: str,
) -> bool:
    """Take each value the site holds in neither form the step holds it in.

    Only names the step holds are read: a name it lacks is one of WDK's own.
    """
    held = encode_params(step.parameters)
    names = [name for name, value in held.items() if wire.get(name, value) != value]
    if not names:
        return False
    decoded = await _decoded(step.id, search_name, wire, record_type, site_id)
    taken = {
        name: decoded[name]
        for name in names
        if name in decoded and decoded[name] != step.parameters[name]
    }
    if not taken:
        return False
    step.parameters = {**step.parameters, **taken}
    return True


async def _decoded(
    step_id: str, search_name: str, wire: Wire, record_type: str, site_id: str
) -> dict[str, ParamValue]:
    """The typed values of one step's wire values, empty when none decode."""
    payload = StrategyAst(
        record_type=record_type,
        root=StrategyStepNode(id=step_id, search_name=search_name),
    )
    try:
        await canonicalize_synced_parameters(
            payload, get_strategy_api(site_id), {step_id: dict(wire)}
        )
    except VEuPathDBError, OSError:
        logger.warning("The site's values did not decode", step_id=step_id)
        return {}
    return dict(payload.root.parameters)


async def _take_the_sites_shape(
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    local_of: Mapping[int, str],
    live: WDKStrategyDetails,
    tree: _SiteTree,
    site_id: str,
) -> bool:
    """Put the site's tree in the place of the tree the site held.

    Only a graph whose whole main tree is on the site has a WDK tree to
    compare, so a graph that holds a draft keeps its own shape.
    """
    held = sync_state.wdk_step_tree
    root_id = graph.primary_root_id()
    if held is None or root_id is None or held == live.step_tree:
        return False
    arrivals = {
        node.id: node
        for node in walk(tree.ast.root)
        if _held_step(graph, local_of, node.id) is None
    }
    if not await _arrivals_decoded(tree, arrivals, site_id):
        return False
    root = _placed(tree.ast.root, graph, local_of)
    placed = flatten_tree(root)
    for gone in set(subtree_ids(root_id, graph.steps)) - placed.keys():
        del graph.steps[gone]
        _forget(sync_state, gone)
    graph.steps.update(placed)
    graph.recompute_roots()
    graph.last_step_id = root.id
    # A step the site added carries no kind, so the catalog says which plugin
    # reads its analysis document.
    await read_the_unread_kinds(site_id=site_id, graph=graph)
    for step_id in arrivals:
        sync_state.wdk_step_ids[step_id] = int(step_id)
    sync_state.wdk_step_tree = live.step_tree
    return True


async def _arrivals_decoded(
    tree: _SiteTree, arrivals: Mapping[str, StrategyStepNode], site_id: str
) -> bool:
    """Decode the values of each step the site added; False when one does not."""
    wire = {
        step_id: tree.wire[step_id] for step_id in arrivals if tree.wire.get(step_id)
    }
    if not wire:
        return True
    try:
        await canonicalize_synced_parameters(tree.ast, get_strategy_api(site_id), wire)
    except VEuPathDBError, OSError:
        logger.warning("The site's added steps did not decode", steps=sorted(wire))
        return False
    return all(arrivals[step_id].parameters for step_id in wire)


def _placed(
    node: StrategyStepNode, graph: StrategyGraph, local_of: Mapping[int, str]
) -> StrategyStepNode:
    """The node the graph holds for a site step, wired as the site wires it."""
    primary = (
        None
        if node.primary_input is None
        else _placed(node.primary_input, graph, local_of)
    )
    secondary = (
        None
        if node.secondary_input is None
        else _placed(node.secondary_input, graph, local_of)
    )
    held = _held_step(graph, local_of, node.id)
    if held is not None:
        own = rebuild_tree(held.id, graph.steps)
        return own.model_copy(
            update={"primary_input": primary, "secondary_input": secondary}
        )
    # WDK names a step it receives without a name after its search.
    return node.model_copy(
        update={
            "primary_input": primary,
            "secondary_input": secondary,
            "search_name": (
                COMBINE_SEARCH_NAME if secondary is not None else node.search_name
            ),
            "display_name": (
                None if node.display_name == node.search_name else node.display_name
            ),
        }
    )


def _forget(sync_state: WDKSyncState, step_id: str) -> None:
    sync_state.wdk_step_ids.pop(step_id, None)
    sync_state.step_counts.pop(step_id, None)
    sync_state.step_validations.pop(step_id, None)
    sync_state.wdk_push_errors.pop(step_id, None)
