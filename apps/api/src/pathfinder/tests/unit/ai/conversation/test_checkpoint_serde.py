"""Checkpoint payloads must survive the serializer the checkpointer runs with.

That serializer decodes the types on the allowlist and nothing else, so a state
type nobody registered fails here rather than on a persisted conversation.
"""

from uuid import UUID

from assistant_core.conversation.serde import (
    CORE_CHECKPOINT_TYPES,
    build_checkpoint_serde,
    checkpoint_types,
)
from assistant_core.graph.turn_state import (
    DurableTaskResult,
    PendingApproval,
    PendingDurableCall,
    SubAgentApprovalCall,
    SubAgentApprovalPending,
    UserQuestionAnswer,
)
from assistant_core.memory.schemas import MemoryValue
from langgraph.checkpoint.serde.event_hooks import (
    SerdeEvent,
    register_serde_event_listener,
)
from pydantic_ai.ui.vercel_ai.request_types import (
    FileUIPart,
    TextUIPart,
    ToolApprovalResponded,
)
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents.state import SearchOverview
from pathfinder.ai.graph.state import (
    FailureCause,
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.assistants.pathfinder_spec import PATHFINDER_CHECKPOINT_TYPES
from pathfinder.domain.separation import AttachedControls, SeparationOffer
from pathfinder.domain.strategy.build_outcome import (
    BuildOutcome,
    NodeResult,
    StepPushFailure,
)
from pathfinder.domain.strategy.constraints import ConstraintKind, ConstraintSource
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.staleness import StaleBuild
from pathfinder.tests._support.checkpoint_state import (
    TABLE_PNG,
    build_outcome,
    domain_state,
    memory_value,
    operational_spec,
    populated_state,
    search_overview,
    user_intent,
    verification_digest,
)
from pathfinder.tests._support.separation import ATTACHED_CONTROLS, recorded_offer
from pathfinder.tests.unit.ai.conversation._checkpoint_samples import (
    pending_approval,
    pending_durable_call,
)

SAMPLES: dict[type, object] = {
    TextUIPart: TextUIPart(text="hello"),
    FileUIPart: TABLE_PNG,
    ToolApprovalResponded: ToolApprovalResponded(id="call_1", approved=True),
    MemoryValue: memory_value(),
    PendingApproval: pending_approval(),
    PendingDurableCall: pending_durable_call(),
    DurableTaskResult: DurableTaskResult(
        task_id=UUID("0c6100d2-0000-4000-8000-000000000001"),
        status="success",
        result={"genesTested": 5511},
    ),
    SubAgentApprovalPending: pending_approval().sub_agent,
    SubAgentApprovalCall: SubAgentApprovalCall(
        tool_call_id="call_delete_step",
        tool_name="delete_step",
        args={"step_id": "s2"},
    ),
    UserQuestionAnswer: UserQuestionAnswer(
        question_id="q1",
        prompt="Fold-change threshold?",
        chosen_labels=["2-fold"],
    ),
    SearchOverview: search_overview("transcript"),
    PhaseDisposition: PhaseDisposition.DONE,
    VerificationDigest: verification_digest(),
    FailureCause: FailureCause.UNRESOLVED_SLOTS,
    IntentClassification: IntentClassification.NEW_STRATEGY,
    UserIntent: user_intent(),
    BuildOutcome: build_outcome(),
    NodeResult: build_outcome().node_results[0],
    StepPushFailure: build_outcome().failed_steps[0],
    ConstraintKind: ConstraintKind.ORGANISM,
    ConstraintSource: ConstraintSource.USER_EXPLICIT,
    CombineOp: CombineOp.INTERSECT,
    OperationalSpec: operational_spec(),
    StaleBuild: StaleBuild(added_nodes=["s3"]),
    StrategyDomainState: domain_state(),
    SeparationOffer: recorded_offer(),
    AttachedControls: ATTACHED_CONTROLS,
}


ALLOWLIST = checkpoint_types(PATHFINDER_CHECKPOINT_TYPES)


def _strict_roundtrip(value: object) -> object:
    """Round trip through the serializer the checkpointer runs with."""
    serde = build_checkpoint_serde(PATHFINDER_CHECKPOINT_TYPES)
    return serde.loads_typed(serde.dumps_typed(value))


def test_every_registered_type_is_a_real_class() -> None:
    # Guards against a typo'd/renamed entry silently dropping off the allowlist.
    assert ALLOWLIST
    for entry in ALLOWLIST:
        assert isinstance(entry, type), entry


def test_the_core_allowlist_holds_no_strategy_type() -> None:
    """A second assistant inherits the core tuple, so science must not be in it."""
    assert set(CORE_CHECKPOINT_TYPES).isdisjoint(
        {
            SearchOverview,
            VerificationDigest,
            OperationalSpec,
            BuildOutcome,
            StrategyDomainState,
        },
    )


def test_the_pathfinder_spec_declares_its_state_types() -> None:
    """The assistant carries the allowlist entries its own state needs."""
    registered = set(ALLOWLIST) - set(CORE_CHECKPOINT_TYPES)
    assert registered == {
        SearchOverview,
        PhaseDisposition,
        VerificationDigest,
        FailureCause,
        IntentClassification,
        UserIntent,
        BuildOutcome,
        NodeResult,
        StepPushFailure,
        ConstraintKind,
        ConstraintSource,
        CombineOp,
        OperationalSpec,
        StaleBuild,
        StrategyDomainState,
        SeparationOffer,
        AttachedControls,
    }


def test_the_allowlist_carries_the_types_a_thread_read_decodes() -> None:
    """Both reach a checkpoint: the disposition on the verification digest, the
    operator on the spec's structure."""
    assert PhaseDisposition in PATHFINDER_CHECKPOINT_TYPES
    assert CombineOp in PATHFINDER_CHECKPOINT_TYPES


def test_every_allowlisted_type_has_a_sample() -> None:
    assert set(ALLOWLIST) == set(SAMPLES)


def test_every_allowlisted_type_survives_strict_roundtrip() -> None:
    for type_, sample in SAMPLES.items():
        assert _strict_roundtrip(sample) == sample, type_


def test_a_populated_state_survives_strict_roundtrip_channel_by_channel() -> None:
    """LangGraph gives every top-level field its own channel, so each field
    value is encoded on its own."""
    state = populated_state()
    for name in PipelineState.model_fields:
        value = getattr(state, name)
        assert _strict_roundtrip(value) == value, name


def test_a_populated_state_rebuilds_from_its_round_tripped_channels() -> None:
    state = populated_state()
    channels = {
        name: _strict_roundtrip(getattr(state, name))
        for name in PipelineState.model_fields
    }
    assert PipelineState.model_validate(channels) == state


def test_a_populated_state_keeps_its_nested_types() -> None:
    restored = _strict_roundtrip(populated_state().domain)
    assert isinstance(restored, StrategyDomainState)
    outcome = restored.last_build_outcome
    assert outcome is not None
    assert isinstance(outcome.failed_steps[0], StepPushFailure)
    assert isinstance(outcome.node_results[0], NodeResult)
    assert isinstance(restored.discovered_searches["GenesByTaxon"], SearchOverview)


def test_a_failed_digest_keeps_its_typed_cause_with_no_blocked_type() -> None:
    """A digest holding ``failure_cause`` decodes the enum itself; the
    serializer blocks no type on the way."""
    digest = VerificationDigest(
        disposition=PhaseDisposition.HANDOFF,
        prose="The check found no answer for two requirements.",
        reason="unresolved slots",
        success=False,
        handoff_to="frame",
        failure_cause=FailureCause.UNRESOLVED_SLOTS,
    )
    events: list[SerdeEvent] = []
    unregister = register_serde_event_listener(events.append)
    try:
        restored = _strict_roundtrip(digest)
    finally:
        unregister()

    assert events == []
    assert restored == digest
    assert isinstance(restored, VerificationDigest)
    assert restored.failure_cause is FailureCause.UNRESOLVED_SLOTS


def test_nested_state_container_survives_strict_roundtrip() -> None:
    # The realistic shape: mixed pathfinder types nested inside plain containers.
    value = {
        "overviews": [search_overview("gene")],
        "kinds": [ConstraintKind.ORGANISM],
    }
    assert _strict_roundtrip(value) == value


def test_tuples_restore_as_lists() -> None:
    # msgpack has no tuple type. Pinned so state that round-trips through a
    # checkpoint is never compared against a tuple and silently mismatched.
    assert _strict_roundtrip((ConstraintKind.ORGANISM,)) == [ConstraintKind.ORGANISM]
