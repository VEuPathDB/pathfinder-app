from __future__ import annotations

from typing import Any, cast

import pytest

from pathfinder.ai.tools.standalone import escape_hatch
from pathfinder.tests._support.rendered_logs import rendered_logs

_REASON = "the researcher at a@b.org asked for microarray data"


async def _overview(ctx: object, **kwargs: object) -> str:
    del ctx, kwargs
    return "overview"


async def test_the_deviation_line_names_the_search_and_not_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(escape_hatch, "get_search_overview", _overview)

    with rendered_logs() as logs:
        await escape_hatch.request_search_inspection(
            cast("Any", None), search_name="GenesByMicroarray", why=_REASON
        )

    line = logs.line(
        "constraint deviation: phase requested out-of-band search inspection"
    )
    assert line["search_name"] == "GenesByMicroarray"
    assert "why" not in line
    assert _REASON not in str(line)
