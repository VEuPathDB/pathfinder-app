"""The values and the shape a strategy holds on the site, taken onto its graph.

The researcher edits the strategy on VEuPathDB as well as here. The graph owns
what the strategy is, so it takes what the site moved before anything is
planned against it or counted on it. Both sides are trees: a stored value is
compared with the site's wire value, with the leaves a push sends for it, and
with its decoded form, never with a spec value.
"""

from __future__ import annotations

from collections.abc import Mapping

from assistant_core.platform.logging import get_logger
from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.parameters import (
    HeldValue,
    ParamValue,
    same_param_value,
    value_kind,
)
from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    StepKind,
    StepSettings,
    StrategyAst,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
    rebuild_tree,
    settings_of,
    subtree_ids,
    walk,
)
from veupathdb.errors import DataParsingError, VEuPathDBError
from veupathdb.wdk import (
    WDKStep,
    WDKStrategyDetails,
    get_strategy_api,
)
from veupathdb_mcp.wdk import (
    WireStep,
    build_snapshot_from_wdk,
    canonicalize_synced_parameters,
)

from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.site_held_settings import SITE_HELD_SETTINGS
from strategist.domain.strategy.step_settings_text import OWN_LINES
from strategist.domain.unread import Unread
from strategist.services.eda.analysis_kinds import read_the_unread_kinds
from strategist.services.site_errors import site_words
from strategist.services.strategies.live_counts import (
    read_the_live_strategy,
)
from strategist.services.strategies.sync_state import WDKSyncState

logger = get_logger(__name__)


__all__ = [
    "SiteEdits",
    "decoded_on_the_site",
    "held_alike",
    "take_the_sites_edits",
    "take_what_the_site_holds",
    "wire_of",
]


class SiteEdits(BaseModel):
    """What the graph took from the site."""

    model_config = ConfigDict(frozen=True)

    valued: list[str] = Field(default_factory=list)
    """The steps whose values the site moved."""
    reshaped: bool = False
    """Whether the graph took the site's tree."""
    not_read: Unread | None = None

    @property
    def moved(self) -> bool:
        return bool(self.valued) or self.reshaped


class TheTurnsOwn(BaseModel):
    """The values a commit's plan moved, which the site's values do not replace."""

    model_config = ConfigDict(frozen=True)

    steps: frozenset[str] = frozenset()
    names: dict[str, frozenset[str]] = Field(default_factory=dict)

    def holds(self, step_id: str, name: str) -> bool:
        return step_id in self.steps or name in self.names.get(step_id, frozenset())


class _SiteTree(BaseModel):
    """The site's tree keyed by WDK step id, with each step's wire values."""

    model_config = ConfigDict(frozen=True)

    ast: StrategyAst
    wire: dict[str, WireStep]


async def take_the_sites_edits(
    *, graph: StrategyGraph, sync_state: WDKSyncState, site_id: str
) -> SiteEdits:
    """Read the strategy on the site and take what it moved.

    A strategy the site does not hold takes nothing; a read that fails takes
    nothing and says why.
    """
    match await read_the_live_strategy(sync_state, site_id):
        case WDKStrategyDetails() as live:
            return await take_what_the_site_holds(
                graph=graph, sync_state=sync_state, site_id=site_id, live=live
            )
        case Unread() as unread:
            return SiteEdits(not_read=unread)
        case _:
            return SiteEdits()


async def take_what_the_site_holds(
    *,
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    site_id: str,
    live: WDKStrategyDetails,
) -> SiteEdits:
    """Write onto the graph the values and the shape ``live`` moved."""
    local_of = {wdk_id: local for local, wdk_id in sync_state.wdk_step_ids.items()}
    match _the_sites_tree(live):
        case Unread() as unread:
            return SiteEdits(not_read=unread)
        case tree:
            pass
    valued = await _take_the_sites_values(
        graph.steps, local_of, live, tree, site_id, TheTurnsOwn()
    )
    match await _take_the_sites_shape(graph, sync_state, local_of, live, tree, site_id):
        case Unread() as unread:
            return SiteEdits(valued=valued, not_read=unread)
        case reshaped:
            pass
    if valued or reshaped:
        logger.info(
            "Took the site's edits onto the graph",
            strategy_id=live.strategy_id,
            valued=valued,
            reshaped=reshaped,
        )
    return SiteEdits(valued=valued, reshaped=reshaped)


def _the_sites_tree(live: WDKStrategyDetails) -> _SiteTree | Unread:
    """The site's tree, or why a step on it is not one the snapshot reads."""
    try:
        ast, wire = build_snapshot_from_wdk(live)
    except (DataParsingError, ValueError) as exc:
        logger.warning("The site's tree is not readable", strategy_id=live.strategy_id)
        return Unread(reason=f"the site's tree was not read: {exc}")
    return _SiteTree(ast=ast, wire=wire)


def _held_step(
    steps: Mapping[str, StrategyStep], local_of: Mapping[int, str], wdk_key: str
) -> StrategyStep | None:
    local = local_of.get(int(wdk_key)) if wdk_key.isdigit() else None
    return None if local is None else steps.get(local)


async def fold_the_sites_values(
    *,
    steps: Mapping[str, StrategyStep],
    sync_state: WDKSyncState,
    live: WDKStrategyDetails,
    site_id: str,
    own: TheTurnsOwn,
) -> list[str]:
    """Take onto ``steps`` every value ``live`` holds that ``own`` does not name."""
    match _the_sites_tree(live):
        case Unread():
            return []
        case tree:
            local_of = {wdk: local for local, wdk in sync_state.wdk_step_ids.items()}
            return await _take_the_sites_values(
                steps, local_of, live, tree, site_id, own
            )


async def _take_the_sites_values(
    steps: Mapping[str, StrategyStep],
    local_of: Mapping[int, str],
    live: WDKStrategyDetails,
    tree: _SiteTree,
    site_id: str,
    own: TheTurnsOwn,
) -> list[str]:
    nodes = {node.id: node for node in walk(tree.ast.root)}
    moved: list[str] = []
    for wdk_key, wdk_step in live.steps.items():
        step = _held_step(steps, local_of, wdk_key)
        if step is None:
            continue
        taken = step.kind is not StepKind.COMBINE and await _take_the_parameters(
            step, wdk_step.search_name, wire_of(wdk_step), site_id=site_id, own=own
        )
        node = nodes.get(wdk_key)
        settled = (
            node is not None
            and (node.infer_kind() == "combine") == (step.kind is StepKind.COMBINE)
            and _take_the_settings(step, settings_of(node), own)
        )
        if taken or settled:
            moved.append(step.id)
    return moved


def wire_of(step: WDKStep) -> WireStep:
    return WireStep(
        record_class=step.record_class_name,
        parameters=dict(step.search_config.parameters),
    )


def _take_the_settings(
    step: StrategyStep, site: StepSettings, own: TheTurnsOwn
) -> bool:
    added = step.filters_wdk_added
    stated = site.model_copy(
        update={
            "filters": step.filters
            if added is None
            else [f for f in site.filters if f not in added]
        }
    )
    held = settings_of(step)
    moved = [
        name
        for name in held.changed(stated)
        if name in SITE_HELD_SETTINGS
        and name not in OWN_LINES
        and not own.holds(step.id, name)
    ]
    taken = dict(stated)
    for name in moved:
        setattr(step, name, taken[name])
    return bool(moved)


async def _take_the_parameters(
    step: StrategyStep,
    search_name: str,
    wire: WireStep,
    *,
    site_id: str,
    own: TheTurnsOwn,
) -> bool:
    """Take each value the site holds in neither form the step holds it in.

    Only names the step holds are read: a name it lacks is one of WDK's own.
    """
    taken = await _differing(step, search_name, wire, site_id, own)
    if not taken:
        return False
    step.parameters = {**step.parameters, **taken}
    return True


async def _differing(
    step: StrategyStep,
    search_name: str,
    wire: WireStep,
    site_id: str,
    own: TheTurnsOwn,
) -> dict[str, ParamValue]:
    names = [
        name
        for name, value in step.parameters.items()
        if name in wire.parameters
        and not own.holds(step.id, name)
        and not held_alike(name, value, HeldValue(wire=wire.parameters[name]))
    ]
    if not names:
        return {}
    match await decoded_on_the_site(step.id, search_name, wire, site_id):
        case Unread():
            return {}
        case decoded:
            return {
                name: decoded[name]
                for name in names
                if name in decoded
                and not held_alike(name, step.parameters[name], decoded[name])
            }


def held_alike(name: str, held: ParamValue, read: ParamValue) -> bool:
    return same_param_value(name, value_kind(held), held, read)


async def decoded_on_the_site(
    step_id: str, search_name: str, wire: WireStep, site_id: str
) -> dict[str, ParamValue] | Unread:
    """The values of one step's wire values, each held as the site holds it
    where no kind reads it."""
    payload = StrategyAst(
        record_type=wire.record_class or "",
        root=StrategyStepNode(id=step_id, search_name=search_name),
    )
    try:
        await canonicalize_synced_parameters(
            payload, get_strategy_api(site_id), {step_id: wire}
        )
    except (VEuPathDBError, OSError) as exc:
        logger.warning("The site's values did not decode", step_id=step_id)
        return Unread(reason=site_words(exc))
    return dict(payload.root.parameters)


async def _take_the_sites_shape(
    graph: StrategyGraph,
    sync_state: WDKSyncState,
    local_of: Mapping[int, str],
    live: WDKStrategyDetails,
    tree: _SiteTree,
    site_id: str,
) -> bool | Unread:
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
        if _held_step(graph.steps, local_of, node.id) is None
    }
    match await _arrivals_decoded(tree, arrivals, site_id):
        case Unread() as unread:
            return unread
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


def _decodable(wire: WireStep) -> bool:
    return bool(wire.parameters)


async def _arrivals_decoded(
    tree: _SiteTree, arrivals: Mapping[str, StrategyStepNode], site_id: str
) -> bool | Unread:
    """Decode the values of each step the site added, or say why they were not."""
    wire = {
        step_id: tree.wire[step_id]
        for step_id in arrivals
        if step_id in tree.wire and _decodable(tree.wire[step_id])
    }
    if not wire:
        return True
    try:
        await canonicalize_synced_parameters(tree.ast, get_strategy_api(site_id), wire)
    except (VEuPathDBError, OSError) as exc:
        logger.warning("The site's added steps did not decode", steps=sorted(wire))
        return Unread(
            reason=f"the steps the site added did not decode: {site_words(exc)}"
        )
    empty = sorted(step_id for step_id in wire if not arrivals[step_id].parameters)
    if empty:
        return Unread(
            reason=f"the steps the site added did not decode: {', '.join(empty)}"
        )
    return True


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
    held = _held_step(graph.steps, local_of, node.id)
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
