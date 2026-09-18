from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.persistence.repositories.background_tasks import (
    BackgroundTaskRepository,
    NewBackgroundTask,
)
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.declaration import durable_impl
from assistant_core.tasks.runner import run_durable_task
from veupathdb.domain.parameters import VocabOption
from veupathdb.wdk import WDKSearchConfig, WDKStep
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.jobs.impls import optimize_params_impl, register_all_tools
from pathfinder.jobs.impls.optimize_params_impl import (
    optimize_search_parameters_impl,
)
from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.parameter_optimization import tunable
from pathfinder.services.parameter_optimization.config import SweepVariantSpec


async def _fake_attach_export(result_json: dict[str, Any], search_name: str) -> None:
    del search_name
    result_json["downloads"] = {"jsonUrl": "https://ex/sweep.json"}


class _Api:
    """A strategy API that answers the built step under test."""

    async def find_step(self, step_id: int, user_id: str | None = None) -> WDKStep:
        del user_id
        return WDKStep(
            id=step_id,
            search_name="GenesByExpression",
            record_class_name="transcript",
            search_config=WDKSearchConfig(),
        )


async def _two_term_knob(
    site_id: str, record_type: str, search_name: str
) -> list[ParameterInfo]:
    del site_id, record_type, search_name
    return [
        ParameterInfo(
            name="knob",
            display_name="knob",
            type="single-pick-vocabulary",
            required=True,
            is_visible=True,
            help="",
            value_format="",
            allowed_values=[
                VocabOption(value="a", display="a"),
                VocabOption(value="b", display="b"),
            ],
        )
    ]


async def _fake_run_single_trial(
    variant: SweepVariantSpec,
    *,
    progress: Any,
    **_kwargs: Any,
) -> dict[str, Any]:
    """Stand-in trial - emits two progress rows so the runner round-trip
    persists progress under the variant scope."""
    await progress.update(
        percent=0.5,
        message=f"halfway {variant.id}",
        data={"phase": "mid"},
    )
    await progress.update(
        percent=1.0,
        message=f"done {variant.id}",
        data={"phase": "end"},
    )
    return {
        "variantId": variant.id,
        "status": "success",
        "params": variant.params,
        "score": 0.9,
    }


async def _seed_user_chat(user_id: UUID, conversation_id: UUID) -> None:
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=conversation_id,
                user_id=user_id,
                site_id="plasmodb",
                name="",
            )
        )
        await session.commit()


@pytest.fixture
def target_kwargs() -> dict[str, Any]:
    """Inputs sized to produce two variants in the Cartesian sweep."""
    return {
        "wdk_step_id": 440299573,
        "positive_controls": ["PF3D7_1133400", "PF3D7_0102600"],
        "budget": 2,
    }


def test_optimize_search_parameters_registered_in_registry() -> None:
    register_all_tools()

    assert durable_impl("optimize_search_parameters") is optimize_search_parameters_impl


@pytest.mark.asyncio
async def test_run_durable_task_wiring_optimize(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
    monkeypatch: pytest.MonkeyPatch,
    target_kwargs: dict[str, Any],
) -> None:
    """End-to-end: runner submits -> impl fans out -> result row matches sweep shape."""
    del db_cleaner, patch_app_db_engine, worker_seams

    monkeypatch.setattr(
        optimize_params_impl, "attach_sweep_download", _fake_attach_export
    )
    monkeypatch.setattr(
        optimize_params_impl, "run_single_trial", _fake_run_single_trial
    )
    monkeypatch.setattr(optimize_params_impl, "get_strategy_api", lambda _s: _Api())
    monkeypatch.setattr(tunable, "search_parameter_metadata", _two_term_knob)
    register_all_tools()

    user_id = uuid4()
    conversation_id = uuid4()
    await _seed_user_chat(user_id, conversation_id)

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name="optimize_search_parameters",
            args={"args": [], "kwargs": target_kwargs},
            tool_call_id="call_optimize_search_parameters",
            phase_overrides={},
            estimated_duration_seconds=900,
        ),
    )

    await run_durable_task(
        tool_name="optimize_search_parameters",
        task_id=str(task_id),
        thread_id=str(conversation_id),
        args={"args": [], "kwargs": target_kwargs},
    )

    task = await repo.get(task_id=task_id)
    assert task is not None
    assert task.status in ("complete", "resuming", "result_ready")
    assert task.result is not None
    assert task.result["downloads"]["jsonUrl"] == "https://ex/sweep.json"
    variants = task.result["variants"]
    assert len(variants) == 2
    assert {v["variantId"] for v in variants} == {"v0", "v1"}
    assert all(v["status"] == "success" for v in variants)
    assert task.result["best"]["score"] == 0.9
