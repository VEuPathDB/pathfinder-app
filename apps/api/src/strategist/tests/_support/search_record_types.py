"""A catalog that places every search a test names under the transcript record type."""

from __future__ import annotations

import pytest

from strategist.ai.tools.standalone import experiment
from strategist.tests._support.recorded_searches import (
    client_search,
    serve_stated_reads,
)


async def _transcript(site_id: str, search_name: str, record_type: str | None) -> str:
    del site_id, search_name
    return record_type or "transcript"


def serve_transcript_searches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every search under transcript, read by the recorded molecular weight
    definition."""
    monkeypatch.setattr(experiment, "resolve_search_record_type", _transcript)
    serve_stated_reads(monkeypatch, [client_search("search_genes_by_molecular_weight")])
