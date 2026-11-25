from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import StrategyAst, walk

from strategist.services.strategies.stated_sides import unmoved
from strategist.services.strategies.step_push_planner import TheTurn, TurnBaseline
from strategist.services.strategies.sync_state import WDKSyncState


def the_turn(sync_state: WDKSyncState, stated: dict[str, frozenset[str]]) -> TheTurn:
    return TheTurn(
        unfinished=sync_state.wdk_push_errors,
        replaced={sid: fold.before for sid, fold in sync_state.site_fold.items()},
        explicit=stated,
    )


def started_settings(old: StrategyAst | None, turn: TheTurn) -> dict[str, TurnBaseline]:
    if old is None:
        return {}
    return {
        node.id: base
        for root in (old.root, *old.detached_roots)
        for node in walk(root)
        if (base := turn.baseline(node.id, node)) is not None
    }


def unstated(
    values: dict[str, ParamValue],
    held: dict[str, ParamValue],
    started: TurnBaseline | None,
    site: dict[str, ParamValue],
) -> dict[str, ParamValue]:
    kept = {} if started is None else started.started.parameters
    return {
        **{
            name: value
            for name, value in site.items()
            if name not in values and name not in kept and started is not None
        },
        **unmoved(values, held),
        **{
            name: held[name]
            for name, value in values.items()
            if name in held
            and (
                (name in kept and kept[name] == value)
                or (started is not None and started.stale_value(name, value))
            )
        },
    }
