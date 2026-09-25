"""The turn's usage figure counts the model runs beside the Lead."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from assistant_core.platform.types import PaidBy

from pathfinder.ai.capabilities.metering import ModelSpend, SpendMeter
from pathfinder.ai.graph._lead_capture import turn_with_spend
from pathfinder.ai.graph.state import PipelineState


def _turn(tokens: int, cost: str) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        turn_total_tokens=tokens,
        turn_total_cost_usd=Decimal(cost),
    )


def test_a_compaction_is_added_to_the_figure_the_pill_reads() -> None:
    meter = SpendMeter(
        spent=[
            ModelSpend(tokens=300, cost_usd=Decimal("0.002"), paid_by=PaidBy.USER),
        ]
    )
    chunks: list[Any] = []

    charged = turn_with_spend(_turn(1000, "0.01"), meter, chunks.append)

    assert [(c["chunk"]["type"], c["chunk"]["data"]) for c in chunks] == [
        ("data-turn-usage", {"totalTokens": 1300, "costUsd": "0.012"})
    ]
    assert (charged.turn_total_tokens, charged.turn_total_cost_usd) == (
        1300,
        Decimal("0.012"),
    )


def test_a_turn_that_ran_nothing_beside_the_lead_reports_nothing_new() -> None:
    chunks: list[Any] = []
    turn = _turn(1000, "0.01")

    assert turn_with_spend(turn, SpendMeter(), chunks.append) is turn
    assert chunks == []
