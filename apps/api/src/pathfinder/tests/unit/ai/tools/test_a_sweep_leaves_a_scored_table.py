"""A finished sweep leaves one Scored variants table, best setting first."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from pathfinder.ai.tools.standalone import optimization
from pathfinder.services.experiment.scored_comparison import ScoredComparison

_RESULT: dict[str, Any] = json.loads(
    (
        Path(__file__).parents[3]
        / "fixtures"
        / "controls"
        / "signalp_sweep_result.json"
    ).read_text()
)
_TASK = UUID("0c6100d2-0000-4000-8000-0000000000aa")


def _table() -> ScoredComparison:
    chunks = optimization._sweep_chunks_from_result(_RESULT, _TASK, "call_sweep")
    tables = [
        chunk.data
        for chunk in chunks
        if isinstance(chunk, DataChunk) and chunk.type == "data-scored-comparison"
    ]
    assert len(tables) == 1
    return ScoredComparison.model_validate(tables[0])


def test_the_table_ranks_signalp_41_first() -> None:
    table = _table()

    assert [v.label for v in table.variants] == [
        "SignalP-4.1",
        "SignalP-5.0",
        "SignalP-6.0",
    ]
    assert table.winner_label == "SignalP-4.1"
    assert table.objective == "f1"
    best = table.variants[0]
    scores = (best.sensitivity, best.precision, best.f1)
    assert [None if x is None else round(x, 3) for x in scores] == [0.95, 0.987, 0.968]
    assert best.search_name == "GenesWithSignalPeptide"
