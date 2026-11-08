from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.wdk import WDKStrategySummary

from pathfinder.ai.explore import account_reads
from pathfinder.ai.explore.account_reads import AccountStrategies, read_my_strategies
from pathfinder.tests._support.run_context import lead_run_context


def _summary(strategy_id: int, *, saved: bool, modified: str) -> WDKStrategySummary:
    return WDKStrategySummary(
        strategy_id=strategy_id,
        name=f"strategy {strategy_id}",
        root_step_id=strategy_id + 1,
        record_class_name="TranscriptRecordClasses.TranscriptRecordClass",
        estimated_size=strategy_id * 2,
        is_saved=saved,
        last_modified=modified,
    )


@pytest.fixture
def listed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    asked: list[str] = []

    async def _allowed(conversation_id: object, user_id: object) -> bool:
        del conversation_id, user_id
        return True

    async def _strategies(site_id: str) -> list[WDKStrategySummary]:
        asked.append(site_id)
        return [
            _summary(12, saved=True, modified="2026-11-02T10:00:00"),
            _summary(11, saved=False, modified="2026-11-01T10:00:00"),
        ]

    monkeypatch.setattr(account_reads, "standing_leave", _allowed)
    monkeypatch.setattr(account_reads, "account_strategies", _strategies)
    return asked


async def test_the_read_names_saved_strategies_and_unsaved_drafts(
    listed: list[str],
) -> None:
    read = await read_my_strategies(lead_run_context(site_id="plasmodb"))

    strategies = AccountStrategies.model_validate(read.return_value)
    assert listed == ["plasmodb"]
    assert (strategies.site_id, strategies.total, strategies.saved) == (
        "plasmodb",
        2,
        1,
    )
    assert [
        (s.wdk_strategy_id, s.status, s.estimated_size) for s in strategies.strategies
    ] == [
        (12, "saved", 24),
        (11, "unsaved draft", 22),
    ]


async def test_the_read_takes_another_site_by_name(listed: list[str]) -> None:
    read = await read_my_strategies(
        lead_run_context(site_id="plasmodb"), site_id="vectorbase"
    )

    assert listed == ["vectorbase"]
    assert AccountStrategies.model_validate(read.return_value).site_id == "vectorbase"


async def test_a_site_no_deployment_serves_is_named_back(listed: list[str]) -> None:
    with pytest.raises(ModelRetry, match="vectorbase"):
        await read_my_strategies(lead_run_context(), site_id="mosquitodb")

    assert listed == []


async def test_a_long_listing_keeps_its_total(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _allowed(conversation_id: object, user_id: object) -> bool:
        del conversation_id, user_id
        return True

    async def _many(site_id: str) -> list[WDKStrategySummary]:
        del site_id
        return [
            _summary(n, saved=False, modified=f"2026-10-01T00:00:{n % 60:02d}")
            for n in range(1, 379)
        ]

    monkeypatch.setattr(account_reads, "standing_leave", _allowed)
    monkeypatch.setattr(account_reads, "account_strategies", _many)

    read = await read_my_strategies(lead_run_context())

    strategies = AccountStrategies.model_validate(read.return_value)
    assert (strategies.total, strategies.saved, len(strategies.strategies)) == (
        378,
        0,
        50,
    )
    assert [s.wdk_strategy_id for s in strategies.strategies[:2]] == [1, 2]
