from __future__ import annotations

from uuid import UUID

import pytest
from veupathdb_mcp.separation import (
    SeparationProgress,
    SeparationRequest,
    SeparationUpdate,
    TooFewControls,
)

from pathfinder.domain.separation import SeparationReport
from pathfinder.services.evidence import separation as facade

_TASK = UUID("5b0c3c56-8f7c-4d2b-9a43-1f1d2c3e4f50")
_SHORT = TooFewControls(
    positives=4, negatives=2, unresolved_negative=["PF3D7_9999999"], charged_requests=8
)


async def _quiet(update: SeparationUpdate) -> None:
    del update


async def test_too_few_resolved_controls_report_the_ask_and_no_offer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def separate(
        site_id: str,
        request: SeparationRequest,
        *,
        strategy_name: str,
        progress: SeparationProgress,
    ) -> TooFewControls:
        del site_id, request, strategy_name, progress
        return _SHORT

    async def no_sheets(**kwargs: object) -> None:
        del kwargs
        pytest.fail("a run with too few controls reads no sheet")

    monkeypatch.setattr(facade, "separate", separate)
    monkeypatch.setattr(facade, "sheet_params_for_searches", no_sheets)
    request = SeparationRequest(
        positives=["PF3D7_0213400", "PF3D7_0321400", "PF3D7_0902300", "PF3D7_1123100"],
        negatives=["PF3D7_1133400", "PF3D7_0304600", "PF3D7_9999999"],
        mode="exact",
        budget=600,
    )

    report = await facade.separate_controls(
        "plasmodb", request, task_id=_TASK, progress=_quiet
    )

    assert report == SeparationReport(
        task_id=str(_TASK),
        site_id="plasmodb",
        mode="exact",
        offer=None,
        measured=[],
        unresolved_negative=["PF3D7_9999999"],
        shortfall=[_SHORT.sentence],
        charged_requests=8,
        budget=600,
    )
    assert report.summary == f"no strategy assembled; {_SHORT.sentence}"
