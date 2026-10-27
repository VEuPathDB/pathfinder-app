from __future__ import annotations

from collections.abc import Sequence

import pytest

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead import verify_dispatch
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.site_checks import SiteCheck

PASSED = SiteCheck(
    kind="result_count",
    subject="the strategy on the site",
    status="pass",
    evidence="the result holds records on the site",
)


def checked_site(
    monkeypatch: pytest.MonkeyPatch, checks: Sequence[SiteCheck] = (PASSED,)
) -> list[LeadDeps]:
    ran: list[LeadDeps] = []

    async def site_checks(deps: LeadDeps) -> list[SiteCheck]:
        ran.append(deps)
        return list(checks)

    async def no_columns(deps: LeadDeps, agent_deps: AgentDeps) -> list[str]:
        del deps, agent_deps
        return []

    monkeypatch.setattr(verify_dispatch, "site_checks", site_checks)
    monkeypatch.setattr(verify_dispatch, "read_the_columns", no_columns)
    return ran
