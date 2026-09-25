"""The route that offers the signed-in account's own strategies on one site."""

from __future__ import annotations

import pytest
from veupathdb.wdk import WDKStrategySummary

from pathfinder.platform.identity import CONTROL_TEST_STRATEGY_NAME
from pathfinder.transport.http.routers.sites import strategies

SITE = "plasmodb"


def _summary(
    strategy_id: int,
    name: str,
    last_modified: str,
    *,
    is_deleted: bool = False,
) -> WDKStrategySummary:
    return WDKStrategySummary(
        strategy_id=strategy_id,
        name=name,
        root_step_id=strategy_id + 1,
        record_class_name="TranscriptRecordClasses.TranscriptRecordClass",
        estimated_size=132,
        is_saved=True,
        is_deleted=is_deleted,
        last_modified=last_modified,
    )


class _Api:
    """Answers one fixed listing and records how it was asked."""

    def __init__(self, listing: list[WDKStrategySummary]) -> None:
        self._listing = listing
        self.calls = 0
        self.sites: list[str] = []

    async def list_strategies(self) -> list[WDKStrategySummary]:
        self.calls += 1
        return self._listing


def _install(
    monkeypatch: pytest.MonkeyPatch, listing: list[WDKStrategySummary]
) -> _Api:
    api = _Api(listing)

    def _factory(site_id: str) -> _Api:
        api.sites.append(site_id)
        return api

    monkeypatch.setattr(strategies, "get_strategy_api", _factory)
    return api


async def test_the_account_strategies_answer_newest_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        [
            _summary(401, "kinase sweep", "2026-09-10T08:00:00"),
            _summary(403, "secreted proteins", "2026-09-14T17:31:02.5"),
            _summary(402, "gametocyte markers", "2026-09-14T09:12:44"),
        ],
    )

    listed = await strategies.list_account_strategies(SITE)

    assert [item.wdk_strategy_id for item in listed] == [403, 402, 401]
    assert listed[0].name == "secreted proteins"
    assert listed[0].estimated_size == 132
    assert listed[0].is_saved is True


async def test_the_listing_carries_only_what_the_picker_draws(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A field no picker draws is plumbing, so the wire does not carry it."""
    _install(monkeypatch, [_summary(401, "kinase sweep", "2026-09-10T08:00:00")])

    listed = await strategies.list_account_strategies(SITE)

    assert set(listed[0].model_dump(by_alias=True)) == {
        "wdkStrategyId",
        "name",
        "estimatedSize",
        "isSaved",
        "lastModified",
    }


async def test_a_strategy_the_researcher_deleted_is_not_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        [
            _summary(401, "kinase sweep", "2026-09-10T08:00:00"),
            _summary(402, "old sweep", "2026-09-11T08:00:00", is_deleted=True),
        ],
    )

    listed = await strategies.list_account_strategies(SITE)

    assert [item.wdk_strategy_id for item in listed] == [401]


async def test_a_helper_strategy_this_deployment_wrote_is_not_offered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PathFinder writes its own strategies into the same WDK account."""
    _install(
        monkeypatch,
        [
            _summary(401, "kinase sweep", "2026-09-10T08:00:00"),
            _summary(
                777,
                f"__pathfinder_internal__:{CONTROL_TEST_STRATEGY_NAME} 1",
                "2026-09-15T08:00:00",
            ),
        ],
    )

    listed = await strategies.list_account_strategies(SITE)

    assert [item.wdk_strategy_id for item in listed] == [401]


async def test_the_listing_reads_one_site_and_asks_wdk_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``list_strategies`` names no user, so WDK answers the token's account."""
    api = _install(monkeypatch, [_summary(401, "kinase sweep", "2026-09-10T08:00:00")])

    await strategies.list_account_strategies(SITE)

    assert api.calls == 1
    assert api.sites == [SITE]


async def test_an_account_with_no_strategy_answers_an_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, [])

    assert await strategies.list_account_strategies(SITE) == []
