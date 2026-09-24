"""A framed, unbuilt draft whose FRAME pass ended on one question."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.lead_tools import classify_user_intent
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import ConstraintKind, OpenQuestion
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._disagreement_thread import joined, leaf
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

BOUND = ["c_signal", "c_stage", "c_conserved", "c_secreted"]
OPEN = "c_localised"
OPEN_PARAM = "evidence"
QUESTION = OpenQuestion(
    question="No GPI-anchor search is realizable; use signal-peptide evidence?",
    dimension=ConstraintKind.DATA_TYPE,
    recommended_value="signal peptide",
)
ANSWER = "Go with your recommendation"


def _bound(criterion_id: str) -> Criterion:
    return Criterion(
        id=criterion_id,
        text=f"{criterion_id} property",
        search_name=f"GenesBy_{criterion_id}",
        resolved_params={"value": StringValue(value=criterion_id)},
    )


def _localised(evidence: str | None) -> Criterion:
    return Criterion(
        id=OPEN,
        text="localised to the surface",
        search_name="GenesBySignalPeptide",
        resolved_params={}
        if evidence is None
        else {OPEN_PARAM: StringValue(value=evidence)},
        open_params=[]
        if evidence is not None
        else [OpenSlot(criterion_id=OPEN, param_name=OPEN_PARAM)],
    )


def framed(evidence: str | None) -> OperationalSpec:
    """Four bound criteria and the localisation criterion, intersected."""
    root = leaf(BOUND[0])
    for criterion_id in [*BOUND[1:], OPEN]:
        root = joined(CombineOp.INTERSECT, root, leaf(criterion_id))
    return OperationalSpec(
        goal="surface vaccine candidates",
        criteria=[*(_bound(cid) for cid in BOUND), _localised(evidence)],
        structure=SpecStructure(root=root),
    )


def classify(
    deps: LeadDeps,
    kind: IntentClassification = IntentClassification.CLARIFICATION_RESPONSE,
    *,
    call_id: str = "t_classify",
) -> None:
    classify_user_intent(
        run_context_for(deps, call_id),
        UserIntent(classification=kind, inferred_goal="use signal-peptide evidence"),
    )


def draft_deps(
    message: str,
    *,
    domain: StrategyDomainState | None = None,
    strategy_session: StrategySession | None = None,
) -> LeadDeps:
    """A new message on a thread whose draft FRAME asked about and nothing built."""
    state = pipeline_state(
        user_prompt=message,
        domain=domain
        if domain is not None
        else StrategyDomainState(
            operational_spec=framed(None), open_questions=[QUESTION]
        ),
    )
    state.user_message_id = uuid4()
    return lead_deps(state, strategy_session=strategy_session)


def answering_deps() -> LeadDeps:
    """The turn after FRAME asked: the question is answered by this message."""
    deps = draft_deps(ANSWER)
    classify(deps)
    return deps
