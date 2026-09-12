"""The seam between the generic assistant turn and PathFinder's science.

``TurnState``, ``TurnContext`` and ``AssistantDeps`` are what a second
assistant reuses, so a strategy field that lands on one of them is a
regression even when every other test still passes.
"""

from __future__ import annotations

import asyncio
import dataclasses
from uuid import uuid4

import pytest
from assistant_core.graph.runtime import AssistantDeps, TurnContext
from assistant_core.graph.turn_state import TurnState
from pydantic import ValidationError

from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.database import no_database

TURN_FIELDS = {
    "conversation_id",
    "user_id",
    "site_id",
    "mode",
    "user_message_id",
    "user_prompt",
    "user_parts",
    "turn_trace_id",
    "turn_created_at",
    "turn_message_id",
    "turn_start_event_id",
    "turn_total_tokens",
    "turn_total_cost_usd",
    "pending_approval",
    "pending_durable_call",
    "durable_result",
    "durable_results",
    "approval_responses",
    "user_question_answers",
    "retrieved_memories",
    "thread_messages_json",
}

DOMAIN_FIELDS = {
    "user_intent",
    "turn_markers",
    "lead_next_state",
    "operational_spec",
    "spec_before_turn",
    "discovered_searches",
    "verification_digest",
    "last_build_outcome",
    "stale_build",
    "created_gene_sets",
    "open_eda_sheet",
    "eda_analysis",
    "requirements",
    "open_questions",
    "recommendations",
    "original_request",
    "turn_briefing",
    "zero_result_history",
}

STRATEGY_RESOURCES = {
    "strategy_session",
    "tool_sources",
    "agent_state",
    "experiment_id",
    "ledger_summary",
    "service_outage",
    "verification_scope",
}


def test_turn_state_carries_only_the_generic_turn_fields() -> None:
    assert set(TurnState.model_fields) == TURN_FIELDS


def test_turn_state_carries_no_strategy_field() -> None:
    assert set(TurnState.model_fields) & DOMAIN_FIELDS == set()


def test_turn_state_rejects_a_strategy_field_at_the_top_level() -> None:
    with pytest.raises(ValidationError, match="operational_spec"):
        TurnState.model_validate(
            {
                "conversation_id": str(uuid4()),
                "user_id": str(uuid4()),
                "site_id": "plasmodb",
                "mode": "strategy",
                "operational_spec": None,
            },
        )


def test_pipeline_state_is_a_turn_state_plus_one_domain_field() -> None:
    assert issubclass(PipelineState, TurnState)
    assert set(PipelineState.model_fields) == TURN_FIELDS | {"domain"}


def test_pipeline_state_domain_is_the_strategy_domain_model() -> None:
    state = PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
    )
    assert isinstance(state.domain, StrategyDomainState)
    assert set(StrategyDomainState.model_fields) == DOMAIN_FIELDS


def test_pipeline_state_rejects_a_strategy_field_at_the_top_level() -> None:
    with pytest.raises(ValidationError, match="verification_digest"):
        PipelineState.model_validate(
            {
                "conversation_id": str(uuid4()),
                "user_id": str(uuid4()),
                "site_id": "plasmodb",
                "mode": "strategy",
                "verification_digest": None,
            },
        )


def test_turn_context_carries_no_strategy_resource() -> None:
    names = {f.name for f in dataclasses.fields(TurnContext)}
    assert names & STRATEGY_RESOURCES == set()
    assert names == {
        "site_id",
        "user_id",
        "db_session_factory",
        "cancel_event",
        "memory_store",
        "phase_models",
        "phase_reasoning",
    }


def test_context_extends_turn_context_with_the_strategy_resources() -> None:
    assert issubclass(Context, TurnContext)
    added = {f.name for f in dataclasses.fields(Context)} - {
        f.name for f in dataclasses.fields(TurnContext)
    }
    assert added == {
        "strategy_session",
        "tool_sources",
        "experiment_id",
    }


def test_context_is_still_frozen_and_built_by_keyword() -> None:
    ctx = Context(
        site_id="plasmodb",
        user_id=uuid4(),
        strategy_session=StrategySession(site_id="plasmodb"),
        db_session_factory=no_database,
        cancel_event=asyncio.Event(),
    )
    assert dataclasses.is_dataclass(ctx)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.__setattr__("site_id", "toxodb")


def test_assistant_deps_carries_no_strategy_resource() -> None:
    assert set(AssistantDeps.model_fields) & STRATEGY_RESOURCES == set()
    assert set(AssistantDeps.model_fields) == {
        "site_id",
        "user_id",
        "conversation_id",
        "db_session_factory",
        "memory_store",
        "cancel_event",
        "retrieved_memories",
        "tool_repetition_guard",
        "durable_deferrals",
    }


def test_agent_deps_extends_assistant_deps_with_the_strategy_resources() -> None:
    assert issubclass(AgentDeps, AssistantDeps)
    added = set(AgentDeps.model_fields) - set(AssistantDeps.model_fields)
    assert added == STRATEGY_RESOURCES
