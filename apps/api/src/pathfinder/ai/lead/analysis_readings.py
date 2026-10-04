"""The study's names and the compute's counts beside each analysis binding the
turn's specs hold, read once for a binding its document alone stated."""

from __future__ import annotations

from collections.abc import Sequence

import httpx
from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.services.eda.export import read_beside_the_document

logger = get_logger(__name__)

__all__ = ["read_every_unread_analysis"]

type Readings = Sequence[tuple[AnalysisBinding, AnalysisBinding]]


async def read_every_unread_analysis(
    domain: StrategyDomainState, *, site_id: str
) -> None:
    """Give every unread binding on the turn's specs what the study and the
    compute say beside its document.

    A binding whose read fails stays as its document states it, and the next
    turn reads it again.
    """
    unread = _unread(
        (
            domain.operational_spec,
            domain.answered_spec,
            domain.spec_before_turn,
            domain.spec_before_dispatch,
        )
    )
    if not unread:
        return
    readings = [(binding, await _read(site_id, binding)) for binding in unread]
    domain.operational_spec = _with_readings(domain.operational_spec, readings)
    domain.answered_spec = _with_readings(domain.answered_spec, readings)
    domain.spec_before_turn = _with_readings(domain.spec_before_turn, readings)
    domain.spec_before_dispatch = _with_readings(domain.spec_before_dispatch, readings)


def _unread(held: Sequence[OperationalSpec | None]) -> list[AnalysisBinding]:
    """Each distinct unread binding the specs hold, in the order they hold it."""
    found: list[AnalysisBinding] = []
    for spec in held:
        if spec is None:
            continue
        for criterion in spec.criteria:
            binding = criterion.analysis
            if binding is not None and binding.unread() and binding not in found:
                found.append(binding)
    return found


async def _read(site_id: str, binding: AnalysisBinding) -> AnalysisBinding:
    try:
        return await read_beside_the_document(site_id, binding)
    except (VEuPathDBError, httpx.HTTPError) as exc:
        logger.warning(
            "analysis binding unread",
            site_id=site_id,
            dataset_id=binding.dataset_id,
            error=str(exc),
        )
        return binding


def _with_readings(
    spec: OperationalSpec | None, readings: Readings
) -> OperationalSpec | None:
    """The spec with each binding it holds unread replaced by its reading."""
    if spec is None:
        return None
    return spec.model_copy(
        update={
            "criteria": [
                criterion.model_copy(
                    update={
                        "analysis": next(
                            (read for held, read in readings if held == binding),
                            binding,
                        )
                    }
                )
                if (binding := criterion.analysis) is not None
                else criterion
                for criterion in spec.criteria
            ]
        }
    )
