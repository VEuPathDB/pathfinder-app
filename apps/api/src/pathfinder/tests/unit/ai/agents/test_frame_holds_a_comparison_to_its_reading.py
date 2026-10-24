"""FRAME is sent back when the comparison it classed by its reading is bound as
another reading, or as no compare at all."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    InputDatasetValue,
    PhyleticTree,
    StringValue,
)

from pathfinder.ai.agents import frame_compare_checks
from pathfinder.ai.agents.frame_compare_checks import hold_a_comparison_to_its_reading
from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.expression_handles import (
    BuiltPattern,
    expression_handle,
)
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.tests._support.computed_comparison import held_comparison
from pathfinder.tests._support.synthetic_taxonomy import pattern, synthetic_tree
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_EXPRESSION = "FERN>=1 AND MOSS=0"
_PER_GENOME = pattern(
    {
        "kind": "compare",
        "left": {"kind": "codes", "codes": ["FERN"]},
        "right": {"kind": "codes", "codes": ["MOSS"]},
        "reading": "per_genome",
        "condition": "more_than",
    }
)


@pytest.fixture(autouse=True)
def _taxonomy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _tree(site_id: str) -> PhyleticTree | None:
        return synthetic_tree()

    monkeypatch.setattr(frame_compare_checks, "ortho_taxonomy", _tree)


def _context(refusals: int = 0) -> RunContext[AgentDeps]:
    ctx = agent_run_context(site_id="orthomcl")
    state = ctx.deps.agent_state
    state.built_expressions[expression_handle(_EXPRESSION)] = BuiltPattern(
        expression=_EXPRESSION, pattern=_PER_GENOME, reading="per genome"
    )
    state.operational_spec_draft.criteria = [
        Criterion(
            id="c_more",
            text="more proteins per genome in ferns",
            search_name="GroupsByPhyleticPattern",
            resolved_params={
                PHYLETIC_EXPRESSION_PARAM: BoundValue(
                    value=StringValue(value=_EXPRESSION), source="chosen"
                )
            },
        )
    ]
    state.refusals = refusals
    return ctx


async def test_a_comparison_bound_in_another_reading_is_sent_back() -> None:
    ctx = _context()

    with pytest.raises(ModelRetry) as sent_back:
        await hold_a_comparison_to_its_reading(
            ctx, FrameResult(comparison_reading="averages")
        )

    assert str(sent_back.value).startswith(
        "c_more compares FERN (3 genomes) with MOSS (2 genomes) by per_genome, and "
        "the request asks for averages:"
    )
    assert ctx.deps.agent_state.refusals == 1


async def test_a_comparison_bound_in_its_reading_passes() -> None:
    result = FrameResult(comparison_reading="per_genome")

    assert await hold_a_comparison_to_its_reading(_context(), result) == result


async def test_a_request_classed_as_no_comparison_passes() -> None:
    result = FrameResult()

    assert await hold_a_comparison_to_its_reading(_context(), result) == result


async def test_at_the_bound_the_departure_is_a_named_gap() -> None:
    held = await hold_a_comparison_to_its_reading(
        _context(refusals=REFUSALS_PER_CHECK),
        FrameResult(comparison_reading="averages"),
    )

    assert isinstance(held, FrameResult)
    assert [gap.kind for gap in held.gaps] == ["comparison_reading_departs"]
    assert held.gaps[0] == PassGap(
        kind="comparison_reading_departs",
        sentence=(
            "The request compares two genome sets by averages, and the bound "
            "comparison reads another way."
        ),
    )


async def test_a_computed_comparison_bound_in_another_reading_is_sent_back() -> None:
    ctx = agent_run_context(site_id="orthomcl")
    state = ctx.deps.agent_state
    held = held_comparison(_PER_GENOME, date(2026, 10, 25)).model_copy(
        update={"dataset_id": "9001"}
    )
    state.computed_comparisons[held.handle] = held
    state.operational_spec_draft.criteria = [
        Criterion(
            id="c_computed",
            text="more proteins per genome in ferns",
            search_name="GroupsByNameList",
            resolved_params={
                "group_names": BoundValue(
                    value=InputDatasetValue(dataset_id="9001"), source="chosen"
                )
            },
        )
    ]

    with pytest.raises(ModelRetry) as sent_back:
        await hold_a_comparison_to_its_reading(
            ctx, FrameResult(comparison_reading="averages")
        )

    assert str(sent_back.value).startswith(
        "c_computed compares FERN (3 genomes) with MOSS (2 genomes) by per_genome"
    )
