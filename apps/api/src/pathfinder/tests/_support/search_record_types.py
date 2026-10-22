"""A catalog that places every search a test names under the transcript record type."""

from __future__ import annotations

import pytest

from pathfinder.ai.tools.standalone import experiment


async def _transcript(site_id: str, search_name: str, record_type: str | None) -> str:
    del site_id, search_name
    return record_type or "transcript"


def serve_transcript_searches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(experiment, "resolve_search_record_type", _transcript)
