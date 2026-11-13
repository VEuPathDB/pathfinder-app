from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from assistant_core.graph.turn_state import UserQuestionAnswer
from assistant_core.memory.schemas import MemoryEntryDraft, MemoryValue
from pydantic_ai.ui.vercel_ai.request_types import (
    FileUIPart,
    TextUIPart,
    ToolApprovalResponded,
)
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp

from strategist.ai.agents.state import CreatedGeneSet, SearchOverview
from strategist.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from strategist.ai.lead.intent import IntentClassification, UserIntent
from strategist.domain.evidence import VerificationReview
from strategist.domain.site_checks import SiteCheck
from strategist.domain.strategy.build_outcome import (
    BuildOutcome,
    NodeResult,
    StepPushFailure,
)
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    DroppedCriterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.questions import OpenQuestion
from strategist.domain.strategy.staleness import StaleBuild
from strategist.tests._support.bound_values import bound
from strategist.tests._support.separation import (
    ATTACHED_CONTROLS,
    TASK_ID,
    recorded_offer,
)
from strategist.tests.unit.ai.conversation._checkpoint_samples import pending_approval


def search_overview(record_type: str) -> SearchOverview:
    return SearchOverview(
        search_name="GenesByTaxon",
        display_name="Genes by Taxon",
        record_type=record_type,
        description="Organism-scoped gene search",
        parameter_names=["organism"],
        required_params=["organism"],
    )


def memory_value() -> MemoryValue:
    return MemoryValue(
        kind="knowledge",
        name="obp-note",
        summary="OBPs are odorant binding proteins",
        content={"detail": "vectorbase"},
        created_at=datetime(2026, 8, 7, tzinfo=UTC),
    )


def verification_digest() -> VerificationDigest:
    return VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose="Strategy ready.",
        reason="verification successful",
        success=True,
        key_findings=["1234 hits"],
        review=VerificationReview(
            checks=[
                SiteCheck(
                    kind=ConstraintKind.ORGANISM,
                    subject="P. falciparum 3D7",
                    status="pass",
                    evidence="all 1,234 records of step 7 ('Kinases') hold an "
                    "organism the strategy selects: Plasmodium falciparum 3D7 (1,234)",
                    requirement="organism:P. falciparum 3D7",
                )
            ]
        ),
        remember=[
            MemoryEntryDraft(
                name="P. falciparum kinome size",
                summary="1234 kinase hits on plasmodb",
                content={"count": 1234},
                tags=["kinase"],
            ),
        ],
    )


def build_outcome() -> BuildOutcome:
    return BuildOutcome(
        pushed_step_ids=["s1"],
        failed_steps=[
            StepPushFailure(step_id="s2", search_name="GenesByGoTerm", error="500"),
        ],
        wdk_strategy_id=330423363,
        node_results=[
            NodeResult(
                node_id="s1",
                search_name="GenesByTaxon",
                wdk_step_id=1,
                status="ok",
            ),
        ],
    )


def operational_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="find drug targets",
        interpreted_goal="protein kinases in P. falciparum",
        criteria=[
            Criterion(
                id="c1",
                text="kinases",
                search_name="GenesByGoTerm",
                resolved_params=bound({"go_term": StringValue(value="GO:0004672")}),
                open_params=[OpenSlot(criterion_id="c1", param_name="evidence_code")],
            ),
            Criterion(id="c2", text="P. falciparum", search_name="GenesByTaxon"),
        ],
        dropped=[DroppedCriterion(text="host response", reason="no gene search")],
        constraints=[
            Constraint(
                id="0000000000c1",
                kind=ConstraintKind.ORGANISM,
                requested_value="P. falciparum 3D7",
                label="organism",
                source=ConstraintSource.USER_EXPLICIT,
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="c1"),
                    StructureNode(kind="leaf", criterion_id="c2"),
                ],
            ),
        ),
    )


def user_intent() -> UserIntent:
    return UserIntent(
        classification=IntentClassification.NEW_STRATEGY,
        inferred_goal="protein kinases",
    )


def domain_state() -> StrategyDomainState:
    return StrategyDomainState(
        user_intent=user_intent(),
        lead_next_state="complete",
        operational_spec=operational_spec(),
        discovered_searches={"GenesByTaxon": search_overview("transcript")},
        site_verdict=verification_digest(),
        last_build_outcome=build_outcome(),
        stale_build=StaleBuild(added_nodes=["s3"], removed_nodes=["s0"]),
        created_gene_sets=[CreatedGeneSet(id="gs-1", name="kinase hits", gene_count=2)],
        open_questions=[
            OpenQuestion(
                question="Which gametocyte RNA-seq study?",
                dimension=ConstraintKind.DATA_TYPE,
                recommended_value="P. falciparum 3D7 gametocyte RNA-seq",
            ),
        ],
        recommendations=[
            Constraint(
                id="0000000000d1",
                kind=ConstraintKind.DATA_TYPE,
                requested_value="P. falciparum 3D7 gametocyte RNA-seq",
                label="Which gametocyte RNA-seq study?",
                source=ConstraintSource.ASSUMED,
                hard=False,
            ),
        ],
        separation_offers={str(TASK_ID): recorded_offer()},
        attached_controls=ATTACHED_CONTROLS,
    )


TABLE_PNG = FileUIPart(
    media_type="image/png",
    filename="table.png",
    url="data:image/png;base64,iVBORw0KGgo=",
)


def populated_state() -> PipelineState:
    return PipelineState(
        conversation_id=UUID(int=1),
        user_id=UUID(int=2),
        site_id="plasmodb",
        mode="strategy",
        user_message_id=UUID(int=3),
        user_prompt="find drug targets",
        user_parts=[TABLE_PNG, TextUIPart(text="find drug targets", state="done")],
        turn_trace_id=str(UUID(int=4)),
        turn_message_id=UUID(int=5),
        turn_created_at="2026-08-21T00:00:00+00:00",
        turn_start_event_id=7,
        turn_total_tokens=1234,
        turn_total_cost_usd=Decimal("0.0042"),
        pending_approval=pending_approval(),
        approval_responses={
            "call_verify_strategy": ToolApprovalResponded(
                id="call_verify_strategy",
                approved=True,
            ),
        },
        user_question_answers={
            "call_consult": [
                UserQuestionAnswer(
                    question_id="q1",
                    prompt="Fold-change threshold?",
                    chosen_labels=["2-fold"],
                ),
            ],
        },
        retrieved_memories=[memory_value()],
        domain=domain_state(),
    )
