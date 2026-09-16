"""``count_bound_criterion``: the tool server's count, under this product's budget.

What the count itself does with a refusal, a missing total or an expiry is the
tool server's own behaviour and is tested there.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from veupathdb.domain.parameters import ParamValue, StringValue

from pathfinder.services.strategies import wdk_counts
from pathfinder.services.strategies.wdk_counts import (
    COUNT_BUDGET_SECONDS,
    count_bound_criterion,
)


def _params() -> dict[str, ParamValue]:
    return {
        "text_expression": StringValue(value='"variant surface protein"'),
        "document_type": StringValue(value="gene"),
    }


def _serve(monkeypatch: pytest.MonkeyPatch, count: int | None) -> list[dict[str, Any]]:
    """Answer one count, and record how the tool server was asked for it."""
    asked: list[dict[str, Any]] = []

    async def _count(
        site_id: str,
        record_type: str,
        search_name: str,
        parameters: Mapping[str, ParamValue],
        *,
        timeout_seconds: float | None = None,
    ) -> int | None:
        asked.append(
            {
                "siteId": site_id,
                "recordType": record_type,
                "searchName": search_name,
                "parameters": dict(parameters),
                "timeoutSeconds": timeout_seconds,
            }
        )
        return count

    monkeypatch.setattr(wdk_counts, "count_search_answer", _count)
    return asked


@pytest.mark.asyncio
async def test_the_bound_configuration_is_what_gets_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _serve(monkeypatch, 3)

    count = await count_bound_criterion(
        "giardiadb", "transcript", "GenesByText", _params()
    )

    assert count == 3
    assert len(asked) == 1
    assert asked[0]["siteId"] == "giardiadb"
    assert asked[0]["recordType"] == "transcript"
    assert asked[0]["searchName"] == "GenesByText"
    assert asked[0]["parameters"] == _params()


@pytest.mark.asyncio
async def test_the_count_is_read_under_this_products_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _serve(monkeypatch, 128)

    await count_bound_criterion("piroplasmadb", "transcript", "GenesByText", _params())

    assert asked[0]["timeoutSeconds"] == COUNT_BUDGET_SECONDS
    assert COUNT_BUDGET_SECONDS == 5.0


@pytest.mark.asyncio
async def test_a_binding_that_matches_nothing_reports_the_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, 0)

    count = await count_bound_criterion(
        "plasmodb", "transcript", "GenesByText", _params()
    )

    assert count == 0


@pytest.mark.asyncio
async def test_a_count_the_tool_server_could_not_read_stays_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked = _serve(monkeypatch, None)

    count = await count_bound_criterion(
        "giardiadb", "transcript", "GenesByText", _params()
    )

    assert count is None
    assert len(asked) == 1
