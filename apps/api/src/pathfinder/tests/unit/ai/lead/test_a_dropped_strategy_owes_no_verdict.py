from __future__ import annotations

import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStrategyDetails, WDKStrategySummary

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.pre_turn import forget_the_verdict_of_a_dropped_strategy
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies import live_counts
from pathfinder.services.strategies.sync_state import ensure_sync_state

_HELD = 1001
_FAILED = VerificationDigest(
    disposition=PhaseDisposition.DONE,
    prose="Checked.",
    reason="The site serves no search for split genes.",
    success=False,
)
_GONE = WDKError("Strategy ID 1001 does not exist.", status=404)
_PROXY_404 = WDKError("<html>404 Not Found</html>", status=404)


def _summary(strategy_id: int) -> WDKStrategySummary:
    return WDKStrategySummary(
        strategy_id=strategy_id, name="Kinases", root_step_id=strategy_id + 1
    )


class _Site:
    def __init__(
        self, read: WDKError | None, listed: list[int] | WDKError | None
    ) -> None:
        self.read = read
        self.listed = listed
        self.asked: list[str] = []

    async def get_strategy(self, strategy_id: int) -> WDKStrategyDetails:
        self.asked.append(f"get {strategy_id}")
        if self.read is not None:
            raise self.read
        raise AssertionError

    async def list_strategies(self) -> list[WDKStrategySummary]:
        self.asked.append("list")
        match self.listed:
            case WDKError():
                raise self.listed
            case None:
                raise AssertionError
            case ids:
                return [_summary(i) for i in ids]


def _synced() -> StrategySession:
    session = StrategySession("plasmodb")
    sync = ensure_sync_state(session)
    sync.wdk_strategy_id = _HELD
    sync.wdk_step_ids = {"s1": 2002}
    return session


def _judged() -> StrategyDomainState:
    domain = StrategyDomainState()
    domain.record_verdict(_FAILED, revision="r1")
    return domain


@pytest.mark.parametrize(
    ("site", "kept", "asked"),
    [
        (_Site(_GONE, [7, 8]), False, ["get 1001", "list"]),
        (_Site(_GONE, [7, _HELD]), True, ["get 1001", "list"]),
        (
            _Site(_PROXY_404, WDKError("redeploying", status=503)),
            True,
            ["get 1001", "list"],
        ),
        (_Site(WDKError("upstream failed", status=502), None), True, ["get 1001"]),
    ],
    ids=["gone", "listed", "site_down", "silent"],
)
async def test_a_verdict_goes_only_when_the_listing_proves_the_strategy_gone(
    monkeypatch: pytest.MonkeyPatch, site: _Site, kept: bool, asked: list[str]
) -> None:
    monkeypatch.setattr(live_counts, "get_strategy_api", lambda site_id: site)
    domain = _judged()

    await forget_the_verdict_of_a_dropped_strategy(domain, _synced())

    assert (domain.site_verdict is not None, domain.verified_revision) == (
        (kept, "r1") if kept else (False, "")
    )
    assert site.asked == asked


async def test_a_thread_with_no_verdict_reads_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _Site(None, None)
    monkeypatch.setattr(live_counts, "get_strategy_api", lambda site_id: site)

    await forget_the_verdict_of_a_dropped_strategy(StrategyDomainState(), _synced())

    assert site.asked == []
