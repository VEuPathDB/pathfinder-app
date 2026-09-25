"""A revert that moves the subset counts the mutation and forgets the count."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaFilter,
    EdaStringSetFilter,
    EdaSubsetDescriptor,
)

from pathfinder.domain.eda_parts import EdaAnalysisState
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.services.eda import thread_surgery
from pathfinder.services.eda.thread_surgery import restore_thread_binding
from pathfinder.tests._support.database import detached_session

_DATASET = "DS_1234567890"
_ANALYSIS = "a1b2c3d4"


def _filter(value: str) -> EdaStringSetFilter:
    return EdaStringSetFilter(
        entity_id="EUPATH_0000738",
        variable_id="EUPATH_0000054",
        string_set=[value],
    )


def _recorded() -> EdaAnalysisState:
    return EdaAnalysisState(
        site_id="plasmodb",
        dataset_id=_DATASET,
        study_id="STUDY_1234567890",
        analysis_id=_ANALYSIS,
        revision=2,
        study_display_name="Gametocyte panel",
        display_name="gametocyte rows",
        num_filters=1,
        num_computations=0,
        filters=[_filter("gametocyte").model_dump(by_alias=True, mode="json")],
        filter_summaries=["filter 0"],
        entity_counts=[],
        can_export_rows=True,
    )


def _live(filters: Sequence[EdaFilter]) -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=_ANALYSIS,
        study_id=_DATASET,
        num_filters=len(filters),
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(descriptor=list(filters)),
        ),
    )


class _RowWrites:
    """Which row function the restore called for the thread."""

    def __init__(self) -> None:
        self.counted: list[UUID] = []
        self.counted_and_cleared: list[UUID] = []


@pytest.fixture
def rows(monkeypatch: pytest.MonkeyPatch) -> _RowWrites:
    written = _RowWrites()

    async def _bump(session: AsyncSession, *, conversation_id: UUID) -> int:
        del session
        written.counted.append(conversation_id)
        return 3

    async def _changed(session: AsyncSession, *, conversation_id: UUID) -> int:
        del session
        written.counted_and_cleared.append(conversation_id)
        return 3

    monkeypatch.setattr(thread_surgery, "bump_analysis_row", _bump)
    monkeypatch.setattr(thread_surgery, "changed_subset_row", _changed)
    return written


def _wire_restore(
    monkeypatch: pytest.MonkeyPatch, patched: list[list[EdaFilter]]
) -> None:
    async def _newest(
        session: AsyncSession, *, conversation_id: UUID
    ) -> EdaAnalysisState:
        del session, conversation_id
        return _recorded()

    async def _read(site_id: str, *, analysis_id: str) -> EdaAnalysisDetail:
        del site_id, analysis_id
        return _live([_filter("ring")])

    async def _patch(
        site_id: str,
        *,
        analysis_id: str,
        dataset_id: str,
        filters: Sequence[EdaFilter],
    ) -> EdaAnalysisDetail:
        del site_id, analysis_id, dataset_id
        patched.append(list(filters))
        return _live(filters)

    async def _row(
        session: AsyncSession, *, conversation_id: UUID
    ) -> ConversationAnalysisView:
        del session, conversation_id
        return ConversationAnalysisView(
            site_id="plasmodb",
            dataset_id=_DATASET,
            analysis_id=_ANALYSIS,
            revision=2,
            subset_previewed=True,
        )

    monkeypatch.setattr(thread_surgery, "newest_analysis_state", _newest)
    monkeypatch.setattr(thread_surgery, "read_analysis", _read)
    monkeypatch.setattr(thread_surgery, "patch_subset", _patch)
    monkeypatch.setattr(thread_surgery, "read_analysis_row", _row)


async def test_a_revert_that_moves_the_subset_forgets_the_count(
    monkeypatch: pytest.MonkeyPatch, rows: _RowWrites
) -> None:
    """The restored subset is not the one a preview counted."""
    conversation_id = uuid4()
    patched: list[list[EdaFilter]] = []
    _wire_restore(monkeypatch, patched)

    await restore_thread_binding(
        detached_session(),
        conversation_id=conversation_id,
        logged=True,
    )

    assert patched == [[_filter("gametocyte")]]
    assert rows.counted_and_cleared == [conversation_id]
    assert rows.counted == []
