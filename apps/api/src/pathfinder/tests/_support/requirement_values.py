from __future__ import annotations

from collections.abc import Iterable

from pathfinder.domain.strategy.constraints import Constraint


def without_ids(constraints: Iterable[Constraint]) -> list[Constraint]:
    return [c.model_copy(update={"id": ""}) for c in constraints]
