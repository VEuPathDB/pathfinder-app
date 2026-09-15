"""Shared context for the Lead Agent's sub-agent dispatches.

The Lead's ``LeadDeps``, the per-phase model resolution and the budget the
dispatch runs under. The streaming engine lives in ``sub_agent_stream`` and
the tool wrappers in ``sub_agent_dispatch``.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from assistant_core.capabilities.repetition_guard import ToolRepetitionGuard
from assistant_core.graph.turn_state import DurableDeferral, SubAgentApprovalPending
from assistant_core.memory.schemas import MemoryValue
from assistant_core.models.settings import build_model_settings
from pydantic_ai.usage import RunUsage, UsageLimits

from pathfinder.ai.agents.execution import EXECUTION_MODEL, build_execution_agent
from pathfinder.ai.agents.frame import FRAME_MODEL, build_frame_agent
from pathfinder.ai.agents.roles import PhaseRole
from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.agents.tool_vocabulary import build_tool_repetition_guard
from pathfinder.ai.agents.verification import (
    VERIFICATION_MODEL,
    build_verification_agent,
)
from pathfinder.ai.graph.runtime import AgentDeps, Context
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.intent import UserIntent
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.domain.strategy.constraints import (
    CombinationRequest,
    Constraint,
    ConstraintKind,
)
from pathfinder.platform.config import get_settings
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.tiers import PhaseTierConfig, resolve_phase_tier_config

# Binding one criterion costs up to ten calls: find a search, read it, read its
# vocabularies (several reads on a vocabulary-heavy site), set the criterion.
# Reading the ledger and setting the structure are paid once for the pass.
CALLS_PER_CRITERION = 10
STRUCTURE_CALLS = 8
# A pass below the floor cannot recover from a single wrong search. The cap is
# what stops an overstated count from spending a whole turn.
MIN_PHASE_TOOL_CALLS = 40
MAX_PHASE_TOOL_CALLS = 160
_PHASE_TOKEN_LIMIT = 2_000_000


def phase_usage_limits(declared_criteria: int) -> UsageLimits:
    """The ceiling for one sub-agent pass over ``declared_criteria`` criteria."""
    wanted = declared_criteria * CALLS_PER_CRITERION + STRUCTURE_CALLS
    calls = max(MIN_PHASE_TOOL_CALLS, min(MAX_PHASE_TOOL_CALLS, wanted))
    return UsageLimits(
        request_limit=calls,
        tool_calls_limit=calls,
        total_tokens_limit=_PHASE_TOKEN_LIMIT,
    )


# A requirement of one of these kinds states a filter of its own, so it names a
# criterion. A comparator or a record type qualifies a criterion it shares with
# another requirement, so it names none.
CRITERION_SHAPED_KINDS = frozenset(
    {
        ConstraintKind.DATA_TYPE,
        ConstraintKind.ORGANISM,
        ConstraintKind.PERCENTILE,
        ConstraintKind.FOLD_CHANGE,
        ConstraintKind.STATISTICAL_THRESHOLD,
    },
)
# Evidence above the clamp buys nothing, so the floor stops where the ceiling is.
MAX_CRITERIA_FLOOR = MAX_PHASE_TOOL_CALLS // CALLS_PER_CRITERION


def _requirement_floor(requirements: Sequence[Constraint]) -> int:
    """How many criteria a set of requirements names, at least.

    Requirements of criterion-shaped kinds name one criterion per label, and a
    combination names one per term. The larger count stands, because a
    combination names criteria the other requirements also state.
    """
    floor = len({c.label for c in requirements if c.kind in CRITERION_SHAPED_KINDS})
    for requirement in requirements:
        if requirement.kind is not ConstraintKind.COMBINATION:
            continue
        combination = CombinationRequest.parse(requirement.requested_value)
        if combination is not None:
            floor = max(floor, len(combination.terms))
    return floor


def criteria_floor(state: PipelineState) -> int:
    """The smallest criterion count the thread's own statements support.

    The spec the turn started from, the spec the thread holds and the stated
    requirements are all evidence of size. A pass runs at the largest of them
    however few criteria its caller declares.
    """
    domain = state.domain
    counts = [_requirement_floor(domain.requirements)]
    counts.extend(
        len(spec.criteria)
        for spec in (domain.spec_before_turn, domain.operational_spec)
        if spec is not None
    )
    return min(max(counts), MAX_CRITERIA_FLOOR)


# A dispatch builds its own agent, so the map holds factories. The model each
# factory bakes in is a constant, because a default-model read runs after every
# inner tool call and must not construct an agent.
BUILD_SUB_AGENT_BY_ROLE: dict[PhaseRole, Callable[[], Any]] = {
    "frame": build_frame_agent,
    "execution": build_execution_agent,
    "verification": build_verification_agent,
}

SUB_AGENT_MODEL_BY_ROLE: dict[PhaseRole, str] = {
    "frame": FRAME_MODEL,
    "execution": EXECUTION_MODEL,
    "verification": VERIFICATION_MODEL,
}

TOOL_TO_PHASE_ROLE: dict[str, PhaseRole] = {
    "frame_problem": "frame",
    "edit_strategy": "frame",
    "recover_failed_steps": "execution",
    "verify_strategy": "verification",
}

PendingApprovalPhase = Literal["frame", "build", "verification", "lead"]

# The phase name the wire carries for a sub-agent run. It names the phase the
# user sees, not the role that runs it, and one call id carries exactly one of
# these however many chunks report it.
WIRE_PHASE_BY_ROLE: dict[str, PendingApprovalPhase] = {
    "frame": "frame",
    "execution": "build",
    "verification": "verification",
}


def phase_default_model_id(role: PhaseRole) -> str:
    """The phase's model when the user pinned nothing: the configured
    ``(default_provider, default_tier)`` preset, else the model its factory
    bakes in."""
    cfg = _configured_tier_config(role)
    if cfg is not None:
        return cfg.model_id
    return SUB_AGENT_MODEL_BY_ROLE[role]


def _configured_tier_config(role: PhaseRole) -> PhaseTierConfig | None:
    settings = get_settings()
    return resolve_phase_tier_config(
        PATHFINDER_ASSISTANT_ID,
        settings.default_provider,
        settings.default_tier,
        role,
    )


def sub_agent_model_id(tool_name: str) -> str:
    """Model id for a sub-agent tool name. ``build_strategy`` is declarative
    (no LLM); everything else maps to the underlying phase agent's model.
    """
    if tool_name == "build_strategy":
        return "declarative:no-llm"
    role = TOOL_TO_PHASE_ROLE.get(tool_name)
    if role is None:
        return ""
    return phase_default_model_id(role)


def phase_override_kwargs(
    runtime: Context,
    role: PhaseRole,
) -> dict[str, Any]:
    """Resolve the model and the provider settings for a phase run.

    The model is the user pick, else the phase default. Settings always
    accompany it, because caching is provider specific.
    """
    if get_settings().pathfinder_chat_provider.strip().lower() == "mock":
        return {"model": get_mock_model()}
    effective_model = runtime.phase_models.get(role) or phase_default_model_id(role)
    tier_cfg = _configured_tier_config(role)
    effort = runtime.phase_reasoning.get(role) or (
        tier_cfg.reasoning_effort if tier_cfg is not None else None
    )
    return {
        "model": effective_model,
        "model_settings": build_model_settings(effective_model, thinking=effort),
    }


@dataclass(frozen=True)
class SubAgentCallUsage:
    """What one dispatch spent, summed over every pass it ran.

    A dispatch runs more than one pass when a stopped pass continues under the
    same tool call id, and the thread reads one number for the dispatch.
    """

    tokens: int = 0
    cost: Decimal = Decimal(0)

    def plus(self, tokens: int, cost: Decimal) -> SubAgentCallUsage:
        return SubAgentCallUsage(tokens=self.tokens + tokens, cost=self.cost + cost)


@dataclass
class SubAgentRunUsage:
    """Usage from one pass of a sub-agent dispatch.

    Each phase can run a different model, so the cost uses the sub-agent's
    own model pricing, not the Lead's.
    """

    usage: RunUsage
    model_name: str | None
    provider_name: str | None
    provider_url: str | None
    parent_tool_call_id: str


@dataclass(frozen=True)
class SubAgentDurablePark:
    """A sub-agent run parked on durable calls, under the dispatch that ran it.

    ``deferrals`` is keyed by the tool call each worker task answers.
    """

    pending: SubAgentApprovalPending
    deferrals: dict[str, DurableDeferral]


@dataclass
class LeadDeps:
    """The Lead Agent's runtime context.

    Mutates ``state`` in place as sub-agent tools run; the Lead's node
    turns the final ``state`` into a langgraph state delta at turn end.
    """

    state: PipelineState
    intent: UserIntent | None
    runtime: Context
    retrieved_memories: list[MemoryValue]
    record_sub_agent_usage: Callable[[SubAgentRunUsage], None] = field(
        default=lambda _u: None,
    )
    # What each dispatch has spent so far, keyed by its tool call id. The
    # Lead's node owns the mapping and a continued pass reads its baseline.
    sub_agent_usage_by_call: dict[str, SubAgentCallUsage] = field(
        default_factory=dict,
    )
    tool_repetition_guard: ToolRepetitionGuard = field(
        default_factory=build_tool_repetition_guard,
    )
    # Suspended sub-agent runs, keyed by the dispatch tool call that stopped at
    # an approval. The Lead's node checkpoints the run the answer re-enters.
    pending_sub_agent_approvals: dict[str, SubAgentApprovalPending] = field(
        default_factory=dict,
    )
    # Durable calls the Lead's own tools handed to a worker, keyed by the tool
    # call each worker task answers.
    durable_deferrals: dict[str, DurableDeferral] = field(default_factory=dict)
    # Suspended sub-agent runs whose parked calls a worker answers, keyed by
    # the dispatch tool call that holds the run.
    pending_sub_agent_durables: dict[str, SubAgentDurablePark] = field(
        default_factory=dict,
    )
    # A FRAME pass that claimed a ready spec over an empty draft is refused
    # once. The next one is reported to the Lead rather than retried again.
    empty_frame_reported: bool = False
    # Why the last dispatch ended without a delta, cleared when the next one
    # starts. The Lead reads it through the ledger.
    last_phase_stop: PhaseStop | None = None
    # A budget stop that bound something is dispatched again once per turn.
    frame_retried_after_stop: bool = False
    # The workbench gene sets this turn created. Every agent of the turn writes
    # into this one list, and the Lead's node folds it into the domain.
    created_gene_sets: list[CreatedGeneSet] = field(default_factory=list)

    @property
    def conversation_id(self) -> UUID | None:
        """The thread this turn belongs to, as the turn state holds it."""
        return self.state.conversation_id

    @property
    def user_id(self) -> UUID | None:
        """The account this turn acts as."""
        return self.runtime.user_id


def apply_agent_state(deps: LeadDeps, agent_deps: AgentDeps) -> None:
    deps.state.domain.discovered_searches = dict(
        agent_deps.agent_state.discovered_searches,
    )
    draft = agent_deps.agent_state.operational_spec_draft
    if draft.criteria or draft.dropped:
        deps.state.domain.operational_spec = draft
