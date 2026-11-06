"""An offered criterion carries the radio pairs its search declares."""

from __future__ import annotations

from collections.abc import Collection

import pytest
from veupathdb_mcp.catalog import ParameterInfo
from veupathdb_mcp.separation import (
    SeparationProgress,
    SeparationRequest,
    SeparationResult,
    SeparationUpdate,
)

from pathfinder.services.evidence import separation as facade
from pathfinder.services.separation.offer import separation_report
from pathfinder.tests._support.separation import (
    ERYTHROCYTE_INVASION,
    TASK_ID,
    recorded_separation,
)

_GO = {"GenesByGoTerm": {"go_typeahead": "go_term"}}


def test_each_criterion_takes_the_pairs_of_its_search() -> None:
    report = separation_report(
        recorded_separation(ERYTHROCYTE_INVASION),
        task_id=TASK_ID,
        sheets={},
        radio_pairs=_GO,
    )

    assert report.offer is not None
    assert {c.search_name: c.radio_pairs for c in report.offer.spec.criteria} == {
        "GenesByGoTerm": _GO["GenesByGoTerm"],
        "GenesByText": {},
    }


async def _quiet(update: SeparationUpdate) -> None:
    del update


async def test_the_run_reads_the_pairs_of_the_searches_it_measured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def separate(
        site_id: str,
        request: SeparationRequest,
        *,
        strategy_name: str,
        progress: SeparationProgress,
    ) -> SeparationResult:
        del site_id, request, strategy_name, progress
        return recorded_separation(ERYTHROCYTE_INVASION)

    async def no_sheets(**kwargs: object) -> dict[str, list[ParameterInfo]]:
        del kwargs
        return {}

    asked: list[set[str]] = []

    async def pairs(
        site_id: str, search_names: Collection[str]
    ) -> dict[str, dict[str, str]]:
        del site_id
        asked.append(set(search_names))
        return _GO

    monkeypatch.setattr(facade, "separate", separate)
    monkeypatch.setattr(facade, "sheet_params_for_searches", no_sheets)
    monkeypatch.setattr(facade, "radio_pairs_of", pairs)

    report = await facade.separate_controls(
        "plasmodb",
        SeparationRequest(
            positives=["PF3D7_0213400"],
            negatives=["PF3D7_1133400"],
            mode="similar",
            budget=600,
        ),
        task_id=TASK_ID,
        progress=_quiet,
    )

    assert asked == [{"GenesByGoTerm", "GenesByText"}]
    assert report.offer is not None
    assert {c.search_name: c.radio_pairs for c in report.offer.spec.criteria} == {
        "GenesByGoTerm": _GO["GenesByGoTerm"],
        "GenesByText": {},
    }
