from __future__ import annotations

import pytest
from pydantic import JsonValue
from pydantic_ai import ModelRetry
from veupathdb_mcp.catalog import ParameterInfo

from strategist.ai.agents.state import AgentToolState
from strategist.tests.unit.ai.tools.test_frame_spec import (
    bind,
    param_info,
    serve_search,
)

_SEARCH = "GenesByRhythm"
_TEXT = "genes with a daily rhythm"


def _serve(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_search(monkeypatch, _period)


def _period(_context: dict[str, str]) -> list[ParameterInfo]:
    return [
        param_info(
            "period_range",
            "number-range",
            default_value='{"min":"20","max":"28"}',
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "stated", [{"min": 20, "max": 28}, {"min": 20.5, "max": 28}, None]
)
async def test_a_range_binds_with_no_open_slot(
    monkeypatch: pytest.MonkeyPatch, stated: JsonValue
) -> None:
    _serve(monkeypatch)

    result = await bind(AgentToolState(), _SEARCH, {"period_range": stated}, text=_TEXT)

    assert result.open_slots == []


@pytest.mark.asyncio
async def test_a_range_written_as_text_is_sent_back_with_its_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch)

    with pytest.raises(ModelRetry) as retry:
        await bind(AgentToolState(), _SEARCH, {"period_range": "20-28"}, text=_TEXT)

    assert retry.value.message == (
        'period_range takes {"min": number, "max": number}, for example '
        "{'min': 0.0, 'max': 1.0}; it read '20-28'. Nothing was recorded."
    )
