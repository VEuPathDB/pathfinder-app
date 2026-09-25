"""Whether the thread's open analysis moved past the card the thread shows."""

from __future__ import annotations

import pytest
from veupathdb.eda import EdaAnalysisDetail, EdaNotFoundError

from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.services.conversations import thread_activity
from pathfinder.services.conversations.thread_activity import (
    _moved_past,
    _ShownAnalysis,
)

_BOUND = ConversationAnalysisView(
    site_id="plasmodb", dataset_id="DS_53f554ec6a", analysis_id="a1b2c3d4", revision=2
)
_STAMP = "2026-09-24T18:02:11"


def _card(analysis_id: str, revision: int, stamp: str | None = None) -> _ShownAnalysis:
    """The analysis a card names, read from the part as the log stores it."""
    return _ShownAnalysis.model_validate(
        {"analysisId": analysis_id, "revision": revision, "modificationTime": stamp}
    )


def _site_holds(monkeypatch: pytest.MonkeyPatch, stamp: str | None) -> list[str]:
    """The service answers ``stamp``, or refuses when it is None."""
    read: list[str] = []

    async def _read(site_id: str, *, analysis_id: str) -> EdaAnalysisDetail:
        del site_id
        read.append(analysis_id)
        if stamp is None:
            msg = f"GET /users/1/analyses/{analysis_id}: no such analysis"
            raise EdaNotFoundError(msg, 404)
        return EdaAnalysisDetail(
            analysis_id=analysis_id, study_id="DS_53f554ec6a", modification_time=stamp
        )

    monkeypatch.setattr(thread_activity, "read_analysis", _read)
    return read


async def test_a_card_of_another_document_has_moved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = _site_holds(monkeypatch, _STAMP)
    shown = _card("e5f6a7b8", 2, _STAMP)

    assert await _moved_past(_BOUND, shown) is True
    assert read == []


async def test_a_mutation_the_card_has_not_shown_has_moved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = _site_holds(monkeypatch, _STAMP)
    shown = _card("a1b2c3d4", 1, _STAMP)

    assert await _moved_past(_BOUND, shown) is True
    assert read == []


async def test_a_card_with_no_stamp_is_not_compared_with_the_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = _site_holds(monkeypatch, "2026-09-24T18:09:40")
    shown = _card("a1b2c3d4", 2)

    assert await _moved_past(_BOUND, shown) is False
    assert read == []


@pytest.mark.parametrize(
    ("held", "moved"),
    [("2026-09-24T18:09:40", True), (_STAMP, False), ("", False), (None, False)],
)
async def test_the_stamp_the_site_holds_decides(
    monkeypatch: pytest.MonkeyPatch, held: str | None, moved: bool
) -> None:
    read = _site_holds(monkeypatch, held)
    shown = _card("a1b2c3d4", 2, _STAMP)

    assert await _moved_past(_BOUND, shown) is moved
    assert read == ["a1b2c3d4"]
