"""The turn reads the analysis its thread holds open, and its preview."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead import pre_turn
from pathfinder.ai.lead.pre_turn import attach_open_eda_analysis
from pathfinder.domain.eda_thread import ConversationAnalysisView, OpenEdaAnalysis
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import detached_session

_BOUND = ConversationAnalysisView(
    site_id="plasmodb",
    dataset_id="DS_e973eadd57",
    analysis_id="4XlEvvr",
    revision=3,
    subset_previewed=True,
)


def _context() -> Context:
    return Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=detached_session,
        cancel_event=asyncio.Event(),
    )


def _state() -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
    )


def _binding(
    view: ConversationAnalysisView | None,
) -> object:
    async def _read(
        session: AsyncSession, *, conversation_id: UUID
    ) -> ConversationAnalysisView | None:
        del session, conversation_id
        return view

    return _read


async def test_the_turn_carries_the_open_analysis_and_its_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pre_turn, "open_analysis_in", _binding(_BOUND))

    state = await attach_open_eda_analysis(
        _state(), _context(), changed_after_the_card=False
    )

    assert state.domain.open_eda_analysis == OpenEdaAnalysis(
        dataset_id="DS_e973eadd57",
        analysis_id="4XlEvvr",
        subset_previewed=True,
        changed_after_the_card=False,
    )


async def test_the_turn_carries_an_analysis_that_moved_past_its_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pre_turn, "open_analysis_in", _binding(_BOUND))

    state = await attach_open_eda_analysis(
        _state(), _context(), changed_after_the_card=True
    )

    assert state.domain.open_eda_analysis == OpenEdaAnalysis(
        dataset_id="DS_e973eadd57",
        analysis_id="4XlEvvr",
        subset_previewed=True,
        changed_after_the_card=True,
    )


async def test_a_thread_with_no_binding_carries_no_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pre_turn, "open_analysis_in", _binding(None))
    state = _state()
    state.domain.open_eda_analysis = OpenEdaAnalysis(
        dataset_id="DS_e973eadd57",
        analysis_id="4XlEvvr",
        subset_previewed=True,
    )

    briefed = await attach_open_eda_analysis(
        state, _context(), changed_after_the_card=False
    )

    assert briefed.domain.model_dump(include={"open_eda_analysis"}) == {
        "open_eda_analysis": None,
    }
