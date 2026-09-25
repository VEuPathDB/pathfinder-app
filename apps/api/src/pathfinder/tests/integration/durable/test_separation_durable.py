"""A separation run on the worker: one progress lane per measured candidate, the
phase rows on the task's own lane, and the report stored as the task's result.

The runner, the progress emitter and the database are real; the tool server's
run is its recorded answer on plasmodb, replayed with the rows it wrote.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation, TaskProgressRow
from assistant_core.persistence.repositories.background_tasks import (
    BackgroundTaskRepository,
    NewBackgroundTask,
)
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.runner import run_durable_task
from sqlalchemy import select
from veupathdb_mcp.separation import (
    SeparationProgress,
    SeparationRequest,
    SeparationResult,
    SeparationUpdate,
)

from pathfinder.domain.separation import SeparationReport
from pathfinder.jobs.impls import register_all_tools
from pathfinder.persistence.models import User
from pathfinder.platform.identity import (
    PATHFINDER_ASSISTANT_ID,
    SEPARATION_STRATEGY_NAME,
)
from pathfinder.services.evidence import separation
from pathfinder.services.separation.offer import separation_report
from pathfinder.tests._support.separation import SIGNAL_PEPTIDE, recorded_separation

_TOOL = "separate_controls"
_REFERENCE = "https://doi.org/10.1038/nature03069"


async def _seed(user_id: UUID, conversation_id: UUID) -> None:
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


def _phase_rows(result: SeparationResult) -> list[SeparationUpdate]:
    """The rows the tool server wrote on this run, without the measured ones."""
    return [
        SeparationUpdate(
            phase="resolved",
            message="Resolved 80 positive and 40 negative ids",
            data={"positives": 80, "negatives": 40, "unresolved": 0},
        ),
        SeparationUpdate(
            phase="uploaded",
            message="Uploaded the controls as one dataset",
            data={"datasetIds": 120},
        ),
        SeparationUpdate(
            phase="collected",
            message=(
                "Collected 25 candidates: 0 from the thread, 0 from the literature, "
                "10 enrichment terms, 4 product phrases, 11 catalog searches; "
                "10 skipped"
            ),
        ),
        SeparationUpdate(
            phase="assembled",
            message="Assembled the exact strategy from 3 criteria",
            data={"mode": "exact", "leaves": 3},
        ),
        SeparationUpdate(
            phase="confirmed",
            message=(
                "The assembled strategy returns 61 of 80 positives and 2 of 40 "
                f"negatives in {result.result_size:,} genes"
            ),
            data={"recovered": 61, "admitted": 2, "size": result.result_size},
        ),
    ]


@pytest.fixture
def requests(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, SeparationRequest, str]]:
    seen: list[tuple[str, SeparationRequest, str]] = []

    async def _recorded(
        site_id: str,
        request: SeparationRequest,
        *,
        strategy_name: str,
        progress: SeparationProgress,
    ) -> SeparationResult:
        seen.append((site_id, request, strategy_name))
        result = recorded_separation(SIGNAL_PEPTIDE)
        rows = _phase_rows(result)
        for row in rows[:3]:
            await progress(row)
        for measured in result.measured:
            await progress(
                SeparationUpdate(
                    phase="measured",
                    message=(
                        f"{measured.candidate.search_name}: "
                        f"{measured.positive.intersection_count} of 80 positives"
                    ),
                    candidate_id=measured.candidate.id,
                )
            )
        for row in rows[3:]:
            await progress(row)
        return result

    monkeypatch.setattr(separation, "separate", _recorded)
    return seen


async def test_the_worker_stores_the_report_and_a_lane_per_candidate(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
    requests: list[tuple[str, SeparationRequest, str]],
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams
    register_all_tools()
    user_id, conversation_id = uuid4(), uuid4()
    await _seed(user_id, conversation_id)
    result = recorded_separation(SIGNAL_PEPTIDE)
    kwargs = {
        "positive_controls": result.positives,
        "negative_controls": result.negatives,
        "mode": "exact",
        "literature": [{"query": "exported proteins", "reference": _REFERENCE}],
        "budget": 400,
    }
    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name=_TOOL,
            args={"args": [], "kwargs": kwargs},
            tool_call_id="call_separate_controls",
            phase_overrides={},
            estimated_duration_seconds=300,
        ),
    )

    await run_durable_task(
        tool_name=_TOOL,
        task_id=str(task_id),
        thread_id=str(conversation_id),
        args={"args": [], "kwargs": kwargs},
    )

    task = await repo.get(task_id=task_id)
    assert task is not None
    assert task.status == "complete"
    assert task.result is not None
    assert SeparationReport.model_validate(task.result) == separation_report(
        result, task_id=task_id
    )
    ((site_id, request, name),) = requests
    assert (site_id, name, request.mode, request.budget, request.thread) == (
        "plasmodb",
        SEPARATION_STRATEGY_NAME,
        "exact",
        400,
        [],
    )
    assert [p.reference for p in request.literature] == [_REFERENCE]
    async with async_session_factory() as session:
        rows = list(
            (
                await session.scalars(
                    select(TaskProgressRow)
                    .where(TaskProgressRow.task_id == task_id)
                    .order_by(TaskProgressRow.id)
                )
            ).all()
        )
    lanes = sorted(
        {
            str(row.data["candidateId"])
            for row in rows
            if row.data and "candidateId" in row.data
        }
    )
    phases = [
        row.message for row in rows if not row.data or "candidateId" not in row.data
    ]
    assert lanes == sorted(m.candidate.id for m in result.measured)
    assert phases == [row.message for row in _phase_rows(result)]
