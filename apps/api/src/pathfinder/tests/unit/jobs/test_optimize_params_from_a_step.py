"""The sweep worker reads its grid off the step it is given."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from assistant_core.tasks.progress import TaskProgressEmitter
from veupathdb.domain.parameters import VocabOption
from veupathdb.wdk import WDKSearchConfig, WDKStep
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.graph.runtime import Context
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.jobs.impls import optimize_params_impl
from pathfinder.services.evidence.control_sets import UnknownControlSetError
from pathfinder.services.parameter_optimization import tunable
from pathfinder.services.parameter_optimization.config import SweepVariantSpec
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.saved_controls import (
    SAVED_SET_ID,
    saved_set,
    serve_saved_controls,
)

STEP_ID = 440299573
SEARCH = "GenesByExonCount"


def _context() -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )


def _emitter() -> TaskProgressEmitter:
    return TaskProgressEmitter(
        task_id=uuid4(),
        conversation_id=uuid4(),
        session_factory=no_database,
    )


def _param(
    name: str,
    param_type: str,
    *,
    options: list[str] | None = None,
) -> ParameterInfo:
    return ParameterInfo(
        name=name,
        display_name=name,
        type=param_type,
        required=True,
        is_visible=True,
        help="",
        value_format="",
        allowed_values=[VocabOption(value=o, display=o) for o in options or []] or None,
    )


@pytest.fixture(autouse=True)
def swept_variants(monkeypatch: pytest.MonkeyPatch) -> list[SweepVariantSpec]:
    """A step that runs one search, no export, and a trial that calls no WDK."""
    tried: list[SweepVariantSpec] = []

    class _Api:
        async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
            del user_id
            return WDKStep(
                id=step_id,
                search_name=SEARCH,
                record_class_name="transcript",
                search_config=WDKSearchConfig(
                    parameters={"organism": '["pf"]', "scope": "gene"}
                ),
            )

    async def trial(
        variant: SweepVariantSpec, *, progress: Any, **_kwargs: Any
    ) -> dict[str, Any]:
        del progress
        tried.append(variant)
        return {"variantId": variant.id, "status": "success", "score": 0.5}

    async def no_export(result_json: dict[str, Any], search_name: str) -> None:
        del result_json, search_name

    async def no_update(self: TaskProgressEmitter, **kwargs: Any) -> None:
        del self, kwargs

    monkeypatch.setattr(optimize_params_impl, "get_strategy_api", lambda _s: _Api())
    monkeypatch.setattr(optimize_params_impl, "run_single_trial", trial)
    monkeypatch.setattr(optimize_params_impl, "attach_sweep_download", no_export)
    monkeypatch.setattr(TaskProgressEmitter, "update", no_update)
    serve_saved_controls(
        monkeypatch, optimize_params_impl, saved_set(["PF3D7_1133400"])
    )
    return tried


def _catalog(monkeypatch: pytest.MonkeyPatch, parameters: list[ParameterInfo]) -> None:
    async def read(
        site_id: str, record_type: str, search_name: str
    ) -> list[ParameterInfo]:
        del site_id, record_type, search_name
        return parameters

    monkeypatch.setattr(tunable, "search_parameter_metadata", read)


async def _run(**kwargs: Any) -> dict[str, Any]:
    return await optimize_params_impl.optimize_search_parameters_impl(
        context=_context(),
        task_id=uuid4(),
        progress=_emitter(),
        memory_store=None,
        wdk_step_id=STEP_ID,
        control_set_id=SAVED_SET_ID,
        **kwargs,
    )


async def test_the_grid_comes_from_the_steps_own_search(
    swept_variants: list[SweepVariantSpec],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _catalog(
        monkeypatch,
        [
            _param("organism", "multi-pick-vocabulary", options=["pf", "pv"]),
            _param("scope", "single-pick-vocabulary", options=["gene", "transcript"]),
        ],
    )

    result = await _run()

    assert len(result["variants"]) == 4
    assert [sorted(v.params) for v in swept_variants] == [["organism", "scope"]] * 4


async def test_named_parameters_are_the_only_ones_swept(
    swept_variants: list[SweepVariantSpec],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _catalog(
        monkeypatch,
        [
            _param("organism", "multi-pick-vocabulary", options=["pf", "pv"]),
            _param("scope", "single-pick-vocabulary", options=["gene", "transcript"]),
        ],
    )

    await _run(parameters=["scope"])

    swept = {v.params["scope"].to_wire() for v in swept_variants}
    held = {v.params["organism"].to_wire() for v in swept_variants}
    assert swept == {"gene", "transcript"}
    assert held == {'["pf"]'}


async def test_a_step_whose_search_has_nothing_tunable_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _catalog(monkeypatch, [_param("gene_result", "input-step")])

    with pytest.raises(ValueError, match=SEARCH):
        await _run()


async def test_the_budget_caps_the_trials(
    swept_variants: list[SweepVariantSpec],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _catalog(
        monkeypatch,
        [
            _param(
                "organism",
                "multi-pick-vocabulary",
                options=[f"o{i}" for i in range(20)],
            )
        ],
    )

    await _run(budget=6)

    assert len(swept_variants) <= 6


async def test_typed_control_ids_without_a_set_start_no_sweep() -> None:
    payload: dict[str, Any] = {
        "context": _context(),
        "task_id": uuid4(),
        "progress": _emitter(),
        "memory_store": None,
        "wdk_step_id": STEP_ID,
        "positive_controls": ["PF3D7_1133400"],
    }

    with pytest.raises(TypeError, match="control_set_id"):
        await optimize_params_impl.optimize_search_parameters_impl(**payload)


async def test_a_set_that_holds_no_controls_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_saved_controls(monkeypatch, optimize_params_impl, saved_set([]))

    with pytest.raises(ValueError, match="Saved controls holds no controls"):
        await _run()


def _saved_set_sweep(control_set_id: str) -> Any:
    return optimize_params_impl.optimize_search_parameters_impl(
        context=_context(),
        task_id=uuid4(),
        progress=_emitter(),
        memory_store=None,
        wdk_step_id=STEP_ID,
        control_set_id=control_set_id,
    )


async def test_a_sweep_on_a_saved_set_names_the_set_it_scored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _catalog(
        monkeypatch,
        [_param("scope", "single-pick-vocabulary", options=["gene", "transcript"])],
    )
    serve_saved_controls(
        monkeypatch,
        optimize_params_impl,
        saved_set(["PF3D7_1133400"], ["PF3D7_0102600"]),
    )

    result = await _saved_set_sweep(SAVED_SET_ID)

    assert result["controlSet"] == {"id": SAVED_SET_ID, "name": "Saved controls"}
    assert len(result["variants"]) == 2


async def test_a_sweep_on_a_set_the_site_does_not_hold_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_saved_controls(
        monkeypatch, optimize_params_impl, saved_set(["PF3D7_1133400"])
    )

    with pytest.raises(UnknownControlSetError, match="names no control set"):
        await _saved_set_sweep("5f1c6a2e-0000-4000-8000-0000000000aa")
