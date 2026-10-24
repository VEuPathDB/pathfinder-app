from __future__ import annotations

import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKStrategyDetails

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.pre_turn import forget_the_verdict_of_a_dropped_strategy
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies import live_counts
from pathfinder.services.strategies.sync_state import ensure_sync_state

_FAILED = VerificationDigest(
    disposition=PhaseDisposition.DONE,
    prose="Checked.",
    reason="The site serves no search for split genes.",
    success=False,
)


class _Site:
    def __init__(self, error: WDKError | None) -> None:
        self.error = error
        self.read: list[int] = []

    async def get_strategy(self, strategy_id: int) -> WDKStrategyDetails:
        self.read.append(strategy_id)
        if self.error is not None:
            raise self.error
        raise AssertionError


def _synced() -> StrategySession:
    session = StrategySession("plasmodb")
    sync = ensure_sync_state(session)
    sync.wdk_strategy_id = 1001
    sync.wdk_step_ids = {"s1": 2002}
    return session


def _judged() -> StrategyDomainState:
    domain = StrategyDomainState()
    domain.record_verdict(_FAILED, revision="r1")
    return domain


@pytest.mark.parametrize(
    ("error", "kept"),
    [
        (WDKError("Strategy ID 1001 does not exist.", status=404), False),
        (WDKError("upstream failed", status=502), True),
    ],
    ids=["gone", "silent"],
)
async def test_a_strategy_the_site_dropped_takes_its_verdict_with_it(
    monkeypatch: pytest.MonkeyPatch, error: WDKError, kept: bool
) -> None:
    monkeypatch.setattr(live_counts, "get_strategy_api", lambda site: _Site(error))
    domain = _judged()

    await forget_the_verdict_of_a_dropped_strategy(domain, _synced())

    assert (domain.verification_digest is not None, domain.verified_revision) == (
        (kept, "r1") if kept else (False, "")
    )


async def test_a_thread_with_no_verdict_reads_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _Site(None)
    monkeypatch.setattr(live_counts, "get_strategy_api", lambda site_id: site)

    await forget_the_verdict_of_a_dropped_strategy(StrategyDomainState(), _synced())

    assert site.read == []
