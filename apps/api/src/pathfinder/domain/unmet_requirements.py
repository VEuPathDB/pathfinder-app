from __future__ import annotations

from collections.abc import Sequence

from pathfinder.domain.caveats import Gap, RequirementGap


def unmet_requirement_keys(gaps: Sequence[Gap]) -> list[str]:
    unmet: list[str] = []
    for gap in gaps:
        match gap:
            case RequirementGap(status="unmet", key=key) if key:
                unmet.append(key)
    return unmet


__all__ = ["unmet_requirement_keys"]
