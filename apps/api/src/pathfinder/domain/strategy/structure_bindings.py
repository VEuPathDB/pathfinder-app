"""The criteria a spec's structure names that no bound criterion stands for."""

from __future__ import annotations

from pathfinder.domain.strategy.operational_spec import (
    OperationalSpec,
    structure_criteria,
)


def unbound_in_structure(spec: OperationalSpec) -> list[str]:
    """Each named criterion the spec lacks, or holds with no search bound.

    A criterion that waits for its analysis is built by the analysis tools.
    """
    by_id = {criterion.id: criterion for criterion in spec.criteria}
    return sorted(
        cid
        for cid in structure_criteria(spec.structure)
        if cid not in by_id or not (by_id[cid].bound or by_id[cid].pending_analysis)
    )


__all__ = ["unbound_in_structure"]
