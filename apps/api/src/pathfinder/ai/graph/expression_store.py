from __future__ import annotations

from pydantic import TypeAdapter

from pathfinder.ai.graph.state import PipelineState
from pathfinder.domain.strategy.computed_groups import HeldComparison
from pathfinder.domain.strategy.expression_handles import (
    BuiltPattern,
    handles_in,
    spec_handles,
)

_PENDING: TypeAdapter[object] = TypeAdapter(object)


def _pending(state: PipelineState) -> str:
    domain = state.domain
    return _PENDING.dump_json(
        [
            domain.open_questions,
            domain.declined_proposal,
            domain.separation_offers,
            state.pending_approval,
        ]
    ).decode()


def kept_expressions(state: PipelineState) -> dict[str, BuiltPattern]:
    domain = state.domain
    specs = (
        domain.operational_spec,
        domain.answered_spec,
        domain.spec_before_turn,
        domain.spec_before_dispatch,
    )
    referenced = handles_in(_pending(state)).union(
        *(spec_handles(spec) for spec in specs)
    )
    return {
        handle: held
        for handle, held in domain.built_expressions.items()
        if handle in referenced
    }


def kept_comparisons(state: PipelineState) -> dict[str, HeldComparison]:
    referenced = handles_in(_pending(state))
    return {
        handle: held
        for handle, held in state.domain.computed_comparisons.items()
        if handle in referenced
    }


__all__ = ["kept_comparisons", "kept_expressions"]
