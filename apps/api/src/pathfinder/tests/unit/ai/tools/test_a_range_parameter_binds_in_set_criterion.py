from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKSearch
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import _frame_qualifiers
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    bind,
    param_info,
    serve_search,
)

_SEARCH = "GenesByRhythm"
_FORMAT = '{"type": "number-range", "min": <number>, "max": <number>}'
_TEXT = "genes with a daily rhythm"


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_search(monkeypatch, _period)

    async def _no_listing(_site: str, _record_type: str) -> list[WDKSearch]:
        return []

    monkeypatch.setattr(_frame_qualifiers, "get_raw_searches", _no_listing)


def _period(_context: dict[str, str]) -> list[ParameterInfo]:
    return [
        param_info(
            "period_range",
            "number-range",
            default_value='{"min":"20","max":"28"}',
            value_format=_FORMAT,
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stated", ['{"min": 20, "max": 28}', '{"min":"20","max":"28"}', None]
)
async def test_a_range_binds_with_no_open_slot(
    monkeypatch: pytest.MonkeyPatch, stated: str | None
) -> None:
    _serve(monkeypatch)

    result = await bind(AgentToolState(), _SEARCH, {"period_range": stated}, text=_TEXT)

    assert result.open_slots == []


@pytest.mark.asyncio
async def test_a_range_the_kind_cannot_read_is_sent_back_with_its_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)

    with pytest.raises(ModelRetry) as retry:
        await bind(AgentToolState(), _SEARCH, {"period_range": "20-28"}, text=_TEXT)

    assert "period_range" in str(retry.value)
    assert _FORMAT in str(retry.value)
