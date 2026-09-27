"""The control test worker runs the saved set the call names, under the user,
and a check reads only the sets its conversation attached."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import (
    BackgroundTask,
    Conversation,
    TaskProgressRow,
)
from assistant_core.persistence.repositories.background_tasks import (
    BackgroundTaskRepository,
    NewBackgroundTask,
)
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.declaration import durable_impl
from assistant_core.tasks.progress import TaskProgressEmitter
from assistant_core.tasks.runner import run_durable_task
from pydantic_ai.exceptions import ModelRetry
from sqlalchemy import select
from veupathdb_mcp.controls import (
    ControlTargetData,
    ControlTestResult,
    NegativeControls,
    PositiveControls,
)
from veupathdb_mcp.tool_payloads import ControlOutcome, DownloadLinks

from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.verify_dispatch import verification_scope
from pathfinder.ai.tools.standalone.control_sets import use_control_set
from pathfinder.ai.tools.standalone.experiment import run_control_tests_on_step
from pathfinder.ai.tools.standalone.saved_control_sets import (
    ControlSetSummary,
    list_control_sets,
)
from pathfinder.jobs.impls import control_tests_impl, register_all_tools
from pathfinder.jobs.impls.control_tests_impl import (
    run_control_tests_on_step_impl,
)
from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.evidence.control_sets import (
    UnknownControlSetError,
    create_control_set,
    new_control_set,
)
from pathfinder.tests._support.job_context import job_context
from pathfinder.tests._support.run_context import lead_run_context, run_context_for
from pathfinder.tests._support.tool_returns import returned

_POSITIVES = ["PF3D7_1031000", "PF3D7_1222600"]
_NEGATIVES = ["PF3D7_0102600"]


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


async def _save_controls(
    user_id: UUID,
    *,
    site_id: str = "plasmodb",
    name: str = "Signal peptide controls",
) -> str:
    """A control set the user saved on the site, as build_control_set saves it."""
    async with async_session_factory() as session:
        created = await create_control_set(
            session,
            new_control_set(
                name=name,
                site_id=site_id,
                record_type="transcript",
                positive_ids=_POSITIVES,
                negative_ids=_NEGATIVES,
                source="chat",
            ),
            user_id=user_id,
        )
        await session.commit()
    return created.id


_MEASURED: list[tuple[list[str] | None, list[str] | None]] = []


async def _fake_run_step(
    *,
    site_id: str,
    wdk_step_id: int,
    positive_controls: list[str] | None = None,
    negative_controls: list[str] | None = None,
) -> ControlTestResult:
    del site_id
    _MEASURED.append((positive_controls, negative_controls))
    pos = positive_controls or []
    neg = negative_controls or []
    return ControlTestResult(
        site_id="plasmodb",
        record_type="transcript",
        target=ControlTargetData(step_id=wdk_step_id, estimated_size=100),
        positive=PositiveControls(recovered_ids=pos, missed_ids=[]) if pos else None,
        negative=NegativeControls(admitted_ids=[], excluded_ids=neg) if neg else None,
    )


async def _fake_export(result: ControlOutcome, name: str) -> ControlOutcome:
    del name
    result.downloads = DownloadLinks(
        json_url="https://example/export.json",
        expires_in_seconds=3600,
    )
    return result


@pytest.mark.asyncio
async def test_register_all_tools_populates_registry() -> None:
    register_all_tools()
    assert durable_impl("run_control_tests_on_step") is run_control_tests_on_step_impl
    register_all_tools()
    assert durable_impl("run_control_tests_on_step") is run_control_tests_on_step_impl


@pytest.mark.asyncio
async def test_control_tests_impl_emits_progress_and_returns_dict(
    db_cleaner: None,
    patch_app_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_cleaner, patch_app_db_engine
    monkeypatch.setattr(control_tests_impl, "run_step_control_tests", _fake_run_step)
    monkeypatch.setattr(control_tests_impl, "attach_control_downloads", _fake_export)

    user_id = uuid4()
    conversation_id = uuid4()
    task_id = uuid4()
    await _seed_user_chat(user_id, conversation_id)

    async with async_session_factory() as session:
        session.add(
            BackgroundTask(
                id=task_id,
                conversation_id=conversation_id,
                user_id=user_id,
                tool_name="run_control_tests_on_step",
                status="running",
                args={},
                estimated_duration_seconds=10,
            )
        )
        await session.commit()

    progress = TaskProgressEmitter(
        task_id=task_id,
        conversation_id=conversation_id,
        session_factory=async_session_factory,
    )
    control_set_id = await _save_controls(user_id)
    _MEASURED.clear()

    result = await run_control_tests_on_step_impl(
        context=job_context(user_id=user_id),
        task_id=task_id,
        progress=progress,
        memory_store=None,
        wdk_step_id=123,
        control_set_id=control_set_id,
    )

    assert _MEASURED == [(_POSITIVES, _NEGATIVES)]
    assert result["stepId"] == 123
    assert result["positiveIntersection"] == 2
    assert result["negativeControlsCount"] == 1
    assert result["controlSet"] == {
        "id": control_set_id,
        "name": "Signal peptide controls",
    }
    assert result["downloads"]["jsonUrl"] == "https://example/export.json"

    async with async_session_factory() as session:
        rows = list(
            (
                await session.execute(
                    select(TaskProgressRow)
                    .where(TaskProgressRow.task_id == task_id)
                    .order_by(TaskProgressRow.id)
                )
            ).scalars()
        )

    assert len(rows) >= 1
    assert rows[0].percent <= rows[-1].percent


@pytest.mark.asyncio
async def test_run_durable_task_wiring_control_tests_end_to_end(
    db_cleaner: None,
    patch_app_db_engine: None,
    worker_seams: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_cleaner, patch_app_db_engine, worker_seams
    monkeypatch.setattr(control_tests_impl, "run_step_control_tests", _fake_run_step)
    monkeypatch.setattr(control_tests_impl, "attach_control_downloads", _fake_export)
    register_all_tools()

    user_id = uuid4()
    conversation_id = uuid4()
    await _seed_user_chat(user_id, conversation_id)
    control_set_id = await _save_controls(user_id)
    kwargs = {"wdk_step_id": 42, "control_set_id": control_set_id}

    repo = BackgroundTaskRepository(session_factory=async_session_factory)
    task_id = await repo.create(
        task=NewBackgroundTask(
            conversation_id=conversation_id,
            user_id=user_id,
            tool_name="run_control_tests_on_step",
            args={"args": [], "kwargs": kwargs},
            tool_call_id="call_run_control_tests_on_step",
            phase_overrides={},
            estimated_duration_seconds=10,
        ),
    )

    await run_durable_task(
        tool_name="run_control_tests_on_step",
        task_id=str(task_id),
        thread_id=str(conversation_id),
        args={"args": [], "kwargs": kwargs},
    )

    t = await repo.get(task_id=task_id)
    assert t is not None
    assert t.status in ("complete", "resuming", "result_ready")
    result_payload: dict[str, Any] | None = t.result
    assert result_payload is not None
    assert result_payload["stepId"] == 42
    assert result_payload["positiveControlsCount"] == 2
    assert result_payload["controlSet"]["id"] == control_set_id


@pytest.mark.asyncio
async def test_the_worker_refuses_a_set_the_user_did_not_save(
    db_cleaner: None,
    patch_app_db_engine: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del db_cleaner, patch_app_db_engine
    monkeypatch.setattr(control_tests_impl, "run_step_control_tests", _fake_run_step)
    owner = uuid4()
    other = uuid4()
    await _seed_user_chat(owner, uuid4())
    await _seed_user_chat(other, uuid4())
    control_set_id = await _save_controls(owner)
    _MEASURED.clear()

    with pytest.raises(UnknownControlSetError) as refused:
        await run_control_tests_on_step_impl(
            context=job_context(user_id=other),
            task_id=uuid4(),
            progress=TaskProgressEmitter(
                task_id=uuid4(),
                conversation_id=uuid4(),
                session_factory=async_session_factory,
            ),
            memory_store=None,
            wdk_step_id=123,
            control_set_id=control_set_id,
        )

    assert refused.value.detail == (
        f"control_set_id {control_set_id!r} names no control set saved on this "
        "site. The saved control sets: none."
    )
    assert _MEASURED == []


@pytest.mark.asyncio
async def test_a_set_saved_on_another_site_is_refused_with_the_sets_of_this_one(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    await _seed_user_chat(user_id, uuid4())
    here = await _save_controls(user_id)
    elsewhere = await _save_controls(user_id, site_id="toxodb")

    with pytest.raises(UnknownControlSetError) as refused:
        await run_control_tests_on_step_impl(
            context=job_context(user_id=user_id),
            task_id=uuid4(),
            progress=TaskProgressEmitter(
                task_id=uuid4(),
                conversation_id=uuid4(),
                session_factory=async_session_factory,
            ),
            memory_store=None,
            wdk_step_id=123,
            control_set_id=elsewhere,
        )

    assert refused.value.detail == (
        f"control_set_id {elsewhere!r} names no control set saved on this site. "
        f"The saved control sets: {here} (Signal peptide controls)."
    )


@pytest.mark.asyncio
async def test_a_check_reads_only_the_set_its_conversation_attached(
    db_cleaner: None,
    patch_app_db_engine: None,
) -> None:
    del db_cleaner, patch_app_db_engine
    lead = lead_run_context(db_session_factory=async_session_factory)
    user_id = lead.deps.runtime.user_id
    await _seed_user_chat(user_id, lead.deps.state.conversation_id)
    attached = await _save_controls(user_id, name="Kinase controls")
    elsewhere = await _save_controls(user_id, name="Two-gene set")

    await use_control_set(lead, attached)
    checker = agent_deps_for(lead.deps)
    checker.verification_scope = verification_scope(lead.deps, check_id="call_verify")
    ctx = run_context_for(checker, "call_check")

    listed = returned(await list_control_sets(ctx), list[ControlSetSummary])
    with pytest.raises(ModelRetry) as refused:
        await run_control_tests_on_step(ctx, wdk_step_id=42, control_set_id=elsewhere)

    assert [(s.control_set_id, s.name) for s in listed] == [
        (attached, "Kinase controls")
    ]
    assert str(refused.value) == (
        f"control_set_id {elsewhere!r} names no control set attached to this "
        f"conversation. The attached control sets: {attached} (Kinase controls). "
        "A control test runs only on a control set attached to this conversation."
    )
