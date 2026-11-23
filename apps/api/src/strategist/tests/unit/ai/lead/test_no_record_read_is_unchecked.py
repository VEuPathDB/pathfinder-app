from __future__ import annotations

from typing import Any

import pytest
from pydantic_ai import RunContext, ToolFailed

from strategist.ai.graph.state import VerificationDigest
from strategist.ai.lead import verify_dispatch
from strategist.ai.lead.deltas import VerificationDelta
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.ai.lead.verify_dispatch import run_verification
from strategist.ai.tools.standalone import results
from strategist.ai.tools.standalone.results import get_sample_records
from strategist.domain.site_checks import SiteCheck
from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.domain.strategy.session import StrategySession
from strategist.tests._support.held_counts import session_holding
from strategist.tests._support.run_context import run_context_for
from strategist.tests._support.site_checks import PASSED, checked_site
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# The root of diag-vaccine run5 turn 1, whose two sample reads both timed out.
_ROOT = 227355040
_NO_ANSWER = f"no answer within 20.0 s for step {_ROOT}"
_READ = "The sampled records are surface antigens."

pytestmark = pytest.mark.usefixtures("collector")


def _deps() -> LeadDeps:
    session: StrategySession = session_holding("plasmodb", "s1", "GenesByText", 61)
    state = pipeline_state(user_prompt="find vaccine candidates")
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1"], wdk_strategy_id=330558093
    )
    return lead_deps(state, strategy_session=session)


def _samples(monkeypatch: pytest.MonkeyPatch, tries: int) -> None:
    async def _times_out(*_args: object, **_kwargs: object) -> Any:
        raise TimeoutError

    monkeypatch.setattr(results, "_sample", _times_out)

    async def _checker(*, agent_deps: Any, **_kwargs: object) -> VerificationDelta:
        ctx: RunContext[Any] = run_context_for(agent_deps)
        for _ in range(tries):
            with pytest.raises(ToolFailed, match=_NO_ANSWER):
                await get_sample_records(ctx, wdk_step_id=_ROOT, limit=8)
        return VerificationDelta(digest=VerificationDigest(prose=_READ))

    monkeypatch.setattr(verify_dispatch, "stream_sub_agent", _checker)


async def _checked(monkeypatch: pytest.MonkeyPatch, tries: int) -> VerificationDigest:
    checked_site(monkeypatch)
    monkeypatch.setattr(results, "READ_DEADLINE_SECONDS", 20.0)
    _samples(monkeypatch, tries)
    delta = await run_verification(
        deps=_deps(), parent_tool_call_id="call_verify", reason="check it"
    )
    assert isinstance(delta, VerificationDelta)
    return delta.digest


async def test_a_check_whose_every_record_read_failed_is_unchecked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = await _checked(monkeypatch, tries=2)

    assert (digest.success, digest.review.checks) == (
        False,
        [
            PASSED,
            SiteCheck(
                kind="records_read",
                subject="the records of the result",
                status="unchecked",
                evidence="no record was read: the site did not answer 2 record reads",
                why_unchecked="site_unanswered",
            ),
        ],
    )


async def test_a_check_that_read_no_record_leaves_the_verdict_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = await _checked(monkeypatch, tries=0)

    assert (digest.success, digest.review.checks) == (
        True,
        [
            PASSED,
            SiteCheck(
                kind="records_read",
                subject="the records of the result",
                status="unchecked",
                evidence="the check read no record of the result",
                why_unchecked="no_check",
            ),
        ],
    )
