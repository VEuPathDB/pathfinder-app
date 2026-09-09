"""The conversation-to-analysis binding, and the upstream read that follows it."""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from veupathdb.eda.models import EdaAnalysisDetail

from pathfinder.persistence.models import User
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.services.eda import binding

pytestmark = pytest.mark.asyncio

_DATASET = "DS_53f554ec6a"
_ANALYSIS = "t4fszEJ"


class _Analyses:
    """Records the arguments ``read_analysis`` sends upstream."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def get(self, *, user_id: str, analysis_id: str) -> EdaAnalysisDetail:
        self.calls.append((user_id, analysis_id))
        return EdaAnalysisDetail(analysis_id=analysis_id, study_id=_DATASET)


@pytest.fixture
async def conversation_id(db_cleaner: None, patch_app_db_engine: None) -> UUID:
    del db_cleaner, patch_app_db_engine
    user_id = uuid4()
    thread_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID, id=thread_id, user_id=user_id
            )
        )
        await session.commit()
    return thread_id


async def test_an_unbound_thread_has_no_analysis(conversation_id: UUID) -> None:
    assert (
        await binding.bound_conversation_analysis(conversation_id=conversation_id)
        is None
    )


async def test_binding_then_reading_returns_the_reference(
    conversation_id: UUID,
) -> None:
    """The read takes the thread id alone, so a worker job makes the same call."""
    await binding.bind_conversation_analysis(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=_DATASET,
        analysis_id=_ANALYSIS,
    )
    view = await binding.bound_conversation_analysis(conversation_id=conversation_id)
    assert view is not None
    assert (view.site_id, view.dataset_id, view.analysis_id) == (
        "plasmodb",
        _DATASET,
        _ANALYSIS,
    )
    assert view.revision == 0


async def test_a_mutation_bumps_the_revision_the_part_reports(
    conversation_id: UUID,
) -> None:
    await binding.bind_conversation_analysis(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=_DATASET,
        analysis_id=_ANALYSIS,
    )
    assert await binding.bump_analysis_revision(conversation_id=conversation_id) == 1
    assert await binding.bump_analysis_revision(conversation_id=conversation_id) == 2
    view = await binding.bound_conversation_analysis(conversation_id=conversation_id)
    assert view is not None
    assert view.revision == 2


async def test_unbinding_clears_the_thread(conversation_id: UUID) -> None:
    await binding.bind_conversation_analysis(
        conversation_id=conversation_id,
        site_id="plasmodb",
        dataset_id=_DATASET,
        analysis_id=_ANALYSIS,
    )
    await binding.unbind_conversation_analysis(conversation_id=conversation_id)
    assert (
        await binding.bound_conversation_analysis(conversation_id=conversation_id)
        is None
    )


async def test_read_analysis_asks_upstream_with_the_resolved_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The upstream document is the SSOT, so every render reads it."""
    analyses = _Analyses()

    async def resolve(site_id: str) -> str:
        assert site_id == "plasmodb"
        return "9876543"

    monkeypatch.setattr(binding, "get_eda_analyses_client", lambda _s: analyses)
    monkeypatch.setattr(binding, "resolve_eda_user_id", resolve)

    detail = await binding.read_analysis("plasmodb", analysis_id=_ANALYSIS)

    assert analyses.calls == [("9876543", _ANALYSIS)]
    assert detail.analysis_id == _ANALYSIS
    assert detail.study_id == _DATASET
