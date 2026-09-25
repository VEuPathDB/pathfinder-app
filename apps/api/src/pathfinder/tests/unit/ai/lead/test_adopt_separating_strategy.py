"""A yes on the separation card builds the measured spec, replacing a strategy the
thread holds through the path a clear takes, and attaches the controls."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
from pydantic_ai.exceptions import ModelRetry
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead import lead_adoption, sub_agent_dispatch
from pathfinder.ai.lead.card_contract import CARD_TOOLS
from pathfinder.ai.lead.guarantees import TOOL_REVERSIBILITY, Reversibility
from pathfinder.ai.lead.intent_gate import UNCLASSIFIED_TOOLS
from pathfinder.ai.lead.lead_adoption import (
    adopt_separating_strategy,
    unknown_offer_message,
)
from pathfinder.ai.lead.proposal import ADOPT_TOOL
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import conversation
from pathfinder.domain.separation import AttachedControls, SeparationOffer
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.control_sets import ControlSetResponse, NewControlSet
from pathfinder.tests._support.database import detached_session
from pathfinder.tests._support.run_context import run_context_for, turn_runtime
from pathfinder.tests._support.separation import TASK_ID, recorded_offer
from pathfinder.tests.unit.ai.lead.conftest import (
    pipeline_state,
    session_with_one_step,
)

_CONTROL_SET_ID = "5f1c6a2e-0000-4000-8000-00000000c0de"


@dataclass
class _Writes:
    """What the adoption wrote, in order."""

    order: list[str] = field(default_factory=list)
    pushed: list[Any] = field(default_factory=list)
    chunks: list[Any] = field(default_factory=list)
    control_sets: list[NewControlSet] = field(default_factory=list)


@pytest.fixture
def writes(monkeypatch: pytest.MonkeyPatch) -> _Writes:
    seen = _Writes()

    async def _persisted(**_kwargs: object) -> None:
        seen.order.append("cleared")

    async def _built(**kwargs: Any) -> BuildOutcome:
        seen.order.append("built")
        seen.pushed.append(kwargs["root"])
        return BuildOutcome(pushed_step_ids=[kwargs["root"].id])

    async def _created(
        session: AsyncSession, spec: NewControlSet, *, user_id: UUID
    ) -> ControlSetResponse:
        del session
        seen.control_sets.append(spec)
        return ControlSetResponse(
            id=_CONTROL_SET_ID,
            name=spec.name,
            site_id=spec.site_id,
            record_type=spec.record_type,
            positive_ids=spec.positive_ids,
            negative_ids=spec.negative_ids,
            source=spec.source,
            tags=[],
            version=1,
            is_public=False,
            user_id=str(user_id),
            created_at="2026-09-24T00:00:00Z",
        )

    monkeypatch.setattr(
        conversation, "persist_strategy_ast_to_conversation", _persisted
    )
    monkeypatch.setattr(sub_agent_dispatch, "build_strategy_from_spec", _built)
    monkeypatch.setattr(lead_adoption, "create_control_set", _created)
    monkeypatch.setattr(
        sub_agent_dispatch, "get_stream_writer", lambda: seen.chunks.append
    )
    return seen


def _deps(session: StrategySession, *offers: SeparationOffer) -> LeadDeps:
    state = pipeline_state(
        user_prompt="yes",
        domain=StrategyDomainState(
            separation_offers={offer.task_id: offer for offer in offers}
        ),
    )
    runtime = turn_runtime(
        db_session_factory=detached_session,
        strategy_session=session,
        user_id=state.user_id,
    )
    return LeadDeps(state=state, intent=None, runtime=runtime, retrieved_memories=[])


async def test_an_unknown_task_is_refused_with_the_tasks_the_thread_holds(
    writes: _Writes,
) -> None:
    deps = _deps(StrategySession(site_id="plasmodb"), recorded_offer())

    with pytest.raises(ModelRetry) as refused:
        await adopt_separating_strategy(
            run_context_for(deps, "call_adopt"),
            "t-9",
            reply="I will make this change and report what it takes with it.",
        )

    assert str(refused.value) == unknown_offer_message(
        "t-9", {str(TASK_ID): recorded_offer()}
    )
    assert writes.order == []


async def test_a_thread_with_a_strategy_is_cleared_then_built(writes: _Writes) -> None:
    deps = _deps(session_with_one_step(), recorded_offer())

    await adopt_separating_strategy(
        run_context_for(deps, "call_adopt"),
        str(TASK_ID),
        reply="I will make this change and report what it takes with it.",
    )

    assert writes.order == ["cleared", "built"]


async def test_the_build_is_the_measured_spec_with_no_model_in_between(
    writes: _Writes,
) -> None:
    offer = recorded_offer()
    deps = _deps(StrategySession(site_id="plasmodb"), offer)

    delta = await adopt_separating_strategy(
        run_context_for(deps, "call_adopt"),
        str(TASK_ID),
        reply="I will make this change and report what it takes with it.",
    )

    built = deps.state.domain.operational_spec
    assert built is not None
    assert [(c.search_name, c.resolved_params) for c in built.criteria] == [
        (c.search_name, c.resolved_params) for c in offer.spec.criteria
    ]
    assert [c.rationale for c in built.criteria] == [
        c.rationale for c in offer.spec.criteria
    ]
    assert delta.outcome.pushed_step_ids == [writes.pushed[0].id]
    assert deps.state.turn_markers.built is True


async def test_the_controls_are_saved_and_attached(writes: _Writes) -> None:
    offer = recorded_offer()
    deps = _deps(StrategySession(site_id="plasmodb"), offer)

    await adopt_separating_strategy(
        run_context_for(deps, "call_adopt"),
        str(TASK_ID),
        reply="I will make this change and report what it takes with it.",
    )

    positives = sorted([*offer.positive.returned, *offer.positive.not_returned])
    negatives = sorted([*offer.negative.returned, *offer.negative.not_returned])
    (saved,) = writes.control_sets
    assert (saved.source, saved.positive_ids, saved.negative_ids) == (
        "separation",
        positives,
        negatives,
    )
    assert deps.state.domain.attached_controls == AttachedControls(
        task_id=str(TASK_ID),
        control_set_id=_CONTROL_SET_ID,
        positives=positives,
        negatives=negatives,
    )
    assert [c.id for c in deps.state.turn_markers.created_control_sets] == [
        _CONTROL_SET_ID
    ]


async def test_an_offer_the_build_refuses_leaves_the_strategy_standing(
    writes: _Writes,
) -> None:
    offer = recorded_offer()
    unstructured = offer.model_copy(
        update={"spec": offer.spec.model_copy(update={"structure": None})}
    )
    session = session_with_one_step()
    deps = _deps(session, unstructured)

    with pytest.raises(ModelRetry):
        await adopt_separating_strategy(
            run_context_for(deps, "call_adopt"),
            str(TASK_ID),
            reply="I will make this change and report what it takes with it.",
        )

    assert writes.order == []
    graph = session.get_graph(None)
    assert graph is not None
    assert (
        deps.state.domain.operational_spec,
        deps.state.turn_markers.accepted_proposal,
        sorted(graph.steps),
    ) == (None, False, ["step_a"])


def test_the_adoption_is_a_card_a_typed_yes_reaches() -> None:
    assert ADOPT_TOOL in CARD_TOOLS
    assert ADOPT_TOOL in UNCLASSIFIED_TOOLS
    assert (
        TOOL_REVERSIBILITY[ADOPT_TOOL],
        TOOL_REVERSIBILITY["separate_controls"],
    ) == (
        Reversibility.REVISIONED_WRITE,
        Reversibility.DURABLE,
    )
