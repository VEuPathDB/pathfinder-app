"""The sweep derives its grid from a recorded WDK search and scores one trial.

Only the WDK calls are doubles: the parameter metadata is the recorded body of
``GenesByExonCount``, and the grid, the variants and the score are the real ones.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.tasks.progress import TaskProgressEmitter
from veupathdb.testing import FIXTURE_ROOT
from veupathdb.wdk import WDKSearchConfig, WDKSearchResponse, WDKStep
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed
from veupathdb_mcp.controls import (
    ControlTargetData,
    ControlTestResult,
    IntersectionConfig,
    PositiveControls,
)

from pathfinder.ai.graph.runtime import Context
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.jobs.impls import optimize_params_impl
from pathfinder.services.parameter_optimization import sweep, tunable
from pathfinder.tests._support.database import no_database

STEP_ID = 440299573
SEARCH = "GenesByExonCount"
POSITIVES = ["PF3D7_1133400", "PF3D7_0102600", "PF3D7_0930300"]


def _recorded_parameters() -> list[ParameterInfo]:
    raw = json.loads(
        (FIXTURE_ROOT / "wdk" / "search_genes_by_exon_count.json").read_text()
    )
    response = WDKSearchResponse.model_validate(raw["body"])
    return format_param_info_typed(response.search_data.parameters or [])


class _Api:
    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name=SEARCH,
            record_class_name="transcript",
            search_config=WDKSearchConfig(parameters={"scope": "Gene"}),
        )


@pytest.fixture
def recorded_search(monkeypatch: pytest.MonkeyPatch) -> list[IntersectionConfig]:
    """The recorded parameter metadata, and a WDK control call that records itself."""
    called: list[IntersectionConfig] = []
    parameters = _recorded_parameters()

    async def read(
        site_id: str, record_type: str, search_name: str
    ) -> list[ParameterInfo]:
        del site_id, record_type, search_name
        return parameters

    async def controls(
        config: IntersectionConfig,
        positive_controls: list[str] | None = None,
        negative_controls: list[str] | None = None,
    ) -> ControlTestResult:
        del negative_controls
        called.append(config)
        found = positive_controls or []
        return ControlTestResult(
            site_id=config.site_id,
            record_type=config.record_type,
            target=ControlTargetData(
                search_name=config.target_search_name,
                estimated_size=1200,
            ),
            positive=PositiveControls(recovered_ids=found, missed_ids=[])
            if found
            else None,
        )

    async def no_export(result_json: dict[str, Any], search_name: str) -> None:
        del result_json, search_name

    async def no_update(self: TaskProgressEmitter, **kwargs: Any) -> None:
        del self, kwargs

    monkeypatch.setattr(tunable, "search_parameter_metadata", read)
    monkeypatch.setattr(sweep, "run_positive_negative_controls", controls)
    monkeypatch.setattr(optimize_params_impl, "get_strategy_api", lambda _s: _Api())
    monkeypatch.setattr(optimize_params_impl, "attach_sweep_download", no_export)
    monkeypatch.setattr(TaskProgressEmitter, "update", no_update)
    return called


async def test_the_recorded_search_yields_a_scored_grid(
    recorded_search: list[IntersectionConfig],
) -> None:
    result = await optimize_params_impl.optimize_search_parameters_impl(
        context=Context(
            site_id="plasmodb",
            user_id=uuid4(),
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        ),
        task_id=uuid4(),
        progress=TaskProgressEmitter(
            task_id=uuid4(),
            conversation_id=uuid4(),
            session_factory=no_database,
        ),
        memory_store=None,
        wdk_step_id=STEP_ID,
        positive_controls=POSITIVES,
        parameters=["scope"],
        budget=4,
    )

    assert [c.target_search_name for c in recorded_search] == [SEARCH, SEARCH]
    assert [c.target_parameters["scope"].to_wire() for c in recorded_search] == [
        "Gene",
        "Transcript",
    ]
    assert [v["variantId"] for v in result["variants"]] == ["v0", "v1"]
    assert [v["status"] for v in result["variants"]] == ["success", "success"]
    assert result["best"]["score"] == 1.0
    assert result["objective"] == "f1"


async def test_the_budget_thins_the_organism_vocabulary(
    recorded_search: list[IntersectionConfig],
) -> None:
    """The recorded search publishes 90 organism leaves; six trials is six."""
    await optimize_params_impl.optimize_search_parameters_impl(
        context=Context(
            site_id="plasmodb",
            user_id=uuid4(),
            strategy_session=StrategySession(site_id="plasmodb"),
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        ),
        task_id=uuid4(),
        progress=TaskProgressEmitter(
            task_id=uuid4(),
            conversation_id=uuid4(),
            session_factory=no_database,
        ),
        memory_store=None,
        wdk_step_id=STEP_ID,
        positive_controls=POSITIVES,
        parameters=["organism"],
        budget=6,
    )

    assert len(recorded_search) == 6
    assert {c.target_parameters["organism"].type for c in recorded_search} == {
        "multi-pick-vocabulary"
    }
