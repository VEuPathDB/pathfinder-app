"""VERIFY's digest states a control result only as a control test of the turn filed it."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic_ai.messages import ToolCallPart

from pathfinder.ai.agents.verification import build_verification_agent
from pathfinder.ai.graph.runtime import VerificationScope
from pathfinder.ai.graph.turn_records import ControlTestRun, TurnMarkers
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    EvidenceCard,
    EvidenceVerdict,
)
from pathfinder.tests.unit.ai.lead.conftest import RetryRecordingScript
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_NINE_OF_TEN = ControlTestRun(
    tool_call_id="call_controls",
    evidence=ControlTestEvidence(
        tested_label="Kinases",
        wdk_step_id=440299573,
        positive=ControlSetEvidence(
            returned=[f"PF3D7_{index:07d}" for index in range(1133400, 1133409)],
            not_returned=["PF3D7_0102600"],
        ),
    ),
)


def _digest(finding: str) -> dict[str, Any]:
    return {
        "digest": {
            "disposition": "done",
            "prose": "The kinase strategy answers the question.",
            "reason": "Controls read from the step.",
            "success": True,
            "keyFindings": [finding],
        }
    }


async def _verified(
    finding: str, *, markers: TurnMarkers | None = None, check_id: str = "call_v1"
) -> tuple[VerificationDelta, list[str]]:
    ctx = agent_run_context()
    if markers is None:
        ctx.deps.turn_markers.record_control_tests([_NINE_OF_TEN])
    else:
        ctx.deps.turn_markers = markers
    ctx.deps.verification_scope = VerificationScope(check_id=check_id)
    script = RetryRecordingScript(
        ToolCallPart(
            tool_name="final_result",
            args=_digest(finding),
            tool_call_id="call_final",
        )
    )
    agent = build_verification_agent()
    with agent.override(model=script.model()):
        result = await agent.run("Verify the kinase strategy.", deps=ctx.deps)
    assert isinstance(result.output, VerificationDelta)
    return result.output, script.retries


async def test_a_digest_that_overstates_the_recovery_is_corrected_once() -> None:
    digest, retries = await _verified("**10** of 10 positive controls recovered")

    assert len(retries) == 1
    assert (
        "The reply says 10 of 10 positive controls returned; the control results "
        "recorded 9 of 10 positive controls returned."
    ) in retries[0]
    assert digest.digest.key_findings == ["**10** of 10 positive controls recovered"]


async def test_a_digest_that_copies_the_test_passes() -> None:
    _digest_out, retries = await _verified("**9** of 10 positive controls recovered")

    assert retries == []


async def test_a_second_check_in_the_same_message_gets_its_own_correction() -> None:
    markers = TurnMarkers()
    markers.record_control_tests([_NINE_OF_TEN])

    _first, first = await _verified(
        "**10** of 10 positive controls recovered", markers=markers
    )
    _second, second = await _verified(
        "**10** of 10 positive controls recovered",
        markers=markers,
        check_id="call_v2",
    )

    assert (len(first), len(second)) == (1, 1)
    assert markers.refused_digests == ["call_v1", "call_v2"]


async def test_the_last_checks_card_backs_the_digest() -> None:
    ctx = agent_run_context()
    ctx.deps.verification_scope = VerificationScope(
        check_id="call_v2",
        last_card=EvidenceCard(
            check_id="call_v1",
            revision="rev-1",
            site_id="plasmodb",
            checked_at=datetime(2026, 9, 24, 9, 30, tzinfo=UTC),
            site_read="read",
            steps=[],
            controls=[_NINE_OF_TEN.evidence],
            citations=[],
            verdict=EvidenceVerdict(supported=True),
        ),
    )
    script = RetryRecordingScript(
        ToolCallPart(
            tool_name="final_result",
            args=_digest("**9** of 10 positive controls recovered at the last check"),
            tool_call_id="call_final",
        )
    )
    agent = build_verification_agent()
    with agent.override(model=script.model()):
        await agent.run("Verify the kinase strategy.", deps=ctx.deps)

    assert script.retries == []
