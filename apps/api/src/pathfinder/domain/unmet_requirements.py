from __future__ import annotations

from collections.abc import Sequence

from pathfinder.domain.caveats import Gap, RequirementGap


def unmet_requirements(gaps: Sequence[Gap]) -> list[str]:
    unmet: list[str] = []
    for gap in gaps:
        match gap:
            case RequirementGap(status="unmet"):
                unmet.append(gap.text)
    return unmet


__all__ = ["unmet_requirements"]
