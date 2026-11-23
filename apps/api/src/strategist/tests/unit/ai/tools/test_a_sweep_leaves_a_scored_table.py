"""A finished sweep leaves one Scored variants table, best setting first."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.domain.parameters import MultiPickValue, SinglePickValue

from strategist.ai.tools.standalone import optimization
from strategist.domain.evidence import NamedControlSet
from strategist.services.experiment.scored_comparison import ScoredComparison
from strategist.services.parameter_optimization.config import (
    SweepResult,
    SweepVariantResult,
)
from strategist.tests._support.qa_recording import qa_recording

_RESULT: dict[str, Any] = json.loads(
    qa_recording(
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


def test_a_setting_restated_in_another_order_does_not_vary() -> None:
    organisms = ["Plasmodium falciparum 3D7", "Plasmodium vivax P01"]
    variants = [
        SweepVariantResult(
            variant_id=variant_id,
            status="success",
            params={
                "organism": MultiPickValue(values=terms),
                "signalp_version": SinglePickValue(value=version),
            },
        )
        for variant_id, terms, version in (
            ("a", organisms, "SignalP-4.1"),
            ("b", organisms[::-1], "SignalP-5.0"),
        )
    ]

    assert optimization._varied(variants) == ["signalp_version"]


def test_a_sweep_with_no_negatives_says_false_positives_were_not_measured() -> None:
    sweep = SweepResult(
        variants=[
            SweepVariantResult(
                variant_id="v1", status="success", score=0.75, recall=0.75
            )
        ],
        best=None,
        search_name="GenesWithSignalPeptide",
        objective="f1",
        control_set=NamedControlSet(id="cs-1", name="Signal peptide controls"),
    )

    assert optimization.sweep_summary(sweep) == (
        "1 settings tried, best recall 0.750; no negative controls: false "
        "positives not measured"
    )


def test_the_recorded_sweep_summary_names_its_objective() -> None:
    sweep = SweepResult.model_validate(_RESULT["result"])

    assert optimization.sweep_summary(sweep) == "3 settings tried, best f1 0.968"
