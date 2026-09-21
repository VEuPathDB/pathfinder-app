"""The spec a dispatch records at its start, and the spec a refusal puts back."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import DeferredToolResults

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.dispatch_context import (
    record_the_spec_the_dispatch_found,
    refuse_and_restore,
)
from pathfinder.ai.lead.sub_agent_stream import SubAgentResume
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state


def _spec(*criterion_ids: str) -> OperationalSpec:
    return OperationalSpec(
        goal="essential kinases",
        criteria=[Criterion(id=cid, text=cid) for cid in criterion_ids],
    )


def _deps(spec: OperationalSpec | None) -> LeadDeps:
    state = pipeline_state(
        user_prompt="find the kinases",
        domain=StrategyDomainState(operational_spec=spec),
    )
    state.domain.spec_before_turn = None if spec is None else spec.model_copy(deep=True)
    return lead_deps(state)


def _resumed() -> SubAgentResume:
    return SubAgentResume(messages=[], results=DeferredToolResults())


def test_a_fresh_dispatch_records_the_spec_the_strategy_answers_to() -> None:
    """The record is a copy, so a pass that writes the spec leaves it alone."""
    deps = _deps(_spec("step_k1"))

    record_the_spec_the_dispatch_found(deps, resume=None)
    committed = deps.state.domain.operational_spec
    assert committed is not None
    committed.criteria.append(Criterion(id="step_k2", text="blood stages"))

    found = deps.state.domain.spec_before_dispatch
    assert found is not None
    assert [c.id for c in found.criteria] == ["step_k1"]


def test_a_dispatch_over_a_thread_with_no_spec_restores_no_spec() -> None:
    """The dispatch found nothing, so its refusal leaves the thread with nothing."""
    deps = _deps(None)
    record_the_spec_the_dispatch_found(deps, resume=None)
    deps.state.domain.operational_spec = _spec("step_k9")

    with pytest.raises(ModelRetry, match="bind something"):
        refuse_and_restore(deps, "bind something")

    assert deps.state.domain.operational_spec is None
    assert deps.state.domain.spec_before_dispatch is None


def test_a_resumed_dispatch_keeps_the_record_it_parked_with() -> None:
    """The parked pass found the spec; the answer to it does not look again."""
    deps = _deps(_spec("step_k1", "step_k2"))
    deps.state.domain.spec_before_dispatch = _spec("step_k1")

    record_the_spec_the_dispatch_found(deps, resume=_resumed())

    found = deps.state.domain.spec_before_dispatch
    assert found is not None
    assert [c.id for c in found.criteria] == ["step_k1"]


def test_a_refusal_puts_back_the_spec_the_dispatch_found() -> None:
    deps = _deps(_spec("step_k1"))
    record_the_spec_the_dispatch_found(deps, resume=None)
    deps.state.domain.operational_spec = _spec("step_k9")

    with pytest.raises(ModelRetry, match="reframe it"):
        refuse_and_restore(deps, "reframe it")

    restored = deps.state.domain.operational_spec
    assert restored is not None
    assert [c.id for c in restored.criteria] == ["step_k1"]
    assert restored is not deps.state.domain.spec_before_dispatch
