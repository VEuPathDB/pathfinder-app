from collections.abc import Container

from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import (
    StepSettings,
    StrategyAst,
    settings_of,
    walk,
)

from strategist.services.strategies.stated_sides import unmoved


def started_settings(
    old: StrategyAst | None, unfinished: Container[str]
) -> dict[str, StepSettings]:
    if old is None:
        return {}
    return {
        node.id: settings_of(node)
        for root in (old.root, *old.detached_roots)
        for node in walk(root)
        if node.id not in unfinished
    }


def unstated(
    values: dict[str, ParamValue],
    held: dict[str, ParamValue],
    started: StepSettings | None,
) -> dict[str, ParamValue]:
    kept = {} if started is None else started.parameters
    return {
        **unmoved(values, held),
        **{
            name: held[name]
            for name, value in values.items()
            if name in held and name in kept and kept[name] == value
        },
    }
