from __future__ import annotations

from typing import Any

import pytest
from veupathdb.wdk import WDKRecordType, WDKStrategyDetails

from pathfinder.ai.lead import evidence_card, sub_agent_tools, verify_checks
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.ai.tools.toolsets import verification
from pathfinder.services.strategies import record_classes
from pathfinder.services.strategies.site_counts import SiteCounts
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.unit.ai.lead.conftest import final_result_model

UNANSWERED_DIGEST: dict[str, Any] = {
    "digest": {
        "handoffTo": "frame",
        "prose": (
            "The built OrthoMCL strategy correctly selects singleton orthogroups, "
            "but it does not answer the organism-level ranking request."
        ),
        "keyFindings": [
            (
                "The result exposes `abbreviation` (`Taxon Code`) but does not "
                "calculate or rank organism-level singleton counts"
            )
        ],
    }
}
VALID = {"level": "RUNNABLE", "isValid": True}


def serve_the_site(
    monkeypatch: pytest.MonkeyPatch,
    details: WDKStrategyDetails,
    record_types: list[WDKRecordType],
) -> None:
    async def strategy(site_id: str, wdk_strategy_id: int) -> WDKStrategyDetails:
        assert wdk_strategy_id == details.strategy_id
        return details

    async def counts(site_id: str, wdk_strategy_id: int) -> SiteCounts:
        return SiteCounts(
            root_step_id=details.root_step_id,
            counts={s.id: s.estimated_size for s in details.steps.values()},
        )

    async def listed(site_id: str) -> list[WDKRecordType]:
        return record_types

    monkeypatch.setattr(verify_checks, "read_site_strategy", strategy)
    monkeypatch.setattr(evidence_card, "read_step_counts", counts)
    monkeypatch.setattr(record_classes, "get_raw_record_types", listed)


async def verify(
    monkeypatch: pytest.MonkeyPatch, deps: LeadDeps, digest: dict[str, Any]
) -> VerificationDelta:
    monkeypatch.setattr(
        sub_agent_tools, "get_mock_model", lambda: final_result_model(digest)
    )
    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions="Return the digest the script names.",
    ):
        result = await run_verification(
            deps=deps, parent_tool_call_id="lead_call_verify", reason="check it"
        )
    assert isinstance(result, VerificationDelta)
    return result
