from __future__ import annotations

from collections.abc import Sequence

from pathfinder.domain.caveats import Gap
from pathfinder.domain.site_checks import SiteCheckGap


def unmet_requirement_keys(gaps: Sequence[Gap]) -> list[str]:
    unmet: list[str] = []
    for gap in gaps:
        match gap:
            case SiteCheckGap(check=check) if check.requirement:
                unmet.append(check.requirement)
    return unmet


__all__ = ["unmet_requirement_keys"]
