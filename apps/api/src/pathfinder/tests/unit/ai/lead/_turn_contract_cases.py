"""Replies and turn records the turn-contract tests share."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.graph.turn_records import ControlTestRun
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse, LeadTurnState, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
)
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.questions import (
    AskedQuestion,
    OpenQuestion,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.held_counts import session_holding
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    user_intent,
)

CLAIMS_A_CHANGE = "I removed that unfiltered essentiality criterion."
REPORTS_THE_STRATEGY = "The essentiality step filters nothing, so I left it."
BLAMING_REPLY = (
    "I kept every requirement you stated. Please try the build again once the "
    "site finishes refreshing the plan's search bindings; I will then "
    "materialize and verify it without changing these requirements."
)
REAL_FAILURE_REPLY = (
    "VEuPathDB refused the organism value on one step, so the build pushed the "
    "other steps only. Try again later once I re-bind that criterion."
)
CLEAN_REPLY = (
    "The planning pass stopped on its call budget with some criteria still "
    "unbound. I am running it again on the remaining ones."
)
ASKING_REPLY = (
    "The spec needs one value: which gametocyte RNA-seq study should the "
    "expression filter read? I recommend the asexual one."
)
EDA_PROSE = "The piggyBac score could not be mapped to a searchable gene field."
REDIRECT = (
    "I build and check search strategies on the VEuPathDB sites, and run "
    "enrichment, EDA and exports on what they return. Ask me one of those and "
    "I will take it from there."
)
WITH_CODE = "Here you go:\n\n```python\ndef reverse(head):\n    return head\n```\n"
AN_ESSAY = "A linked list is a chain of nodes. " * 20

DATASET = "DS_70dd50fed7"
CRITERION = "essential in blood stages"


def reply(
    prose: str,
    *,
    changed: bool = False,
    next_state: LeadTurnState = "await_user",
    questions: list[AskedQuestion] | None = None,
) -> LeadResponse:
    return LeadResponse(
        prose=prose,
        next_state=next_state,
        strategy_changed=changed,
        asked_questions=list(questions or []),
    )


def kinds(deps: LeadDeps, report: LeadResponse) -> list[str]:
    return [m.kind for m in reconcile(report, turn_record(run_context_for(deps)))]


def reading_deps() -> LeadDeps:
    """A turn that read the strategy and wrote nothing."""
    state = pipeline_state(user_prompt="How does that step define essential?")
    state.user_message_id = uuid4()
    state.turn_markers.intent_classified = True
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["s1", "s2", "s3"],
    )
    return lead_deps(
        state, strategy_session=session_holding("plasmodb", "s3", "GenesByText", 1)
    )


def building_deps(*, verified: bool = True) -> LeadDeps:
    """A turn that pushed a build, checked unless the caller says otherwise."""
    state = pipeline_state(user_prompt="Add an essentiality filter.")
    state.user_message_id = uuid4()
    state.record_build(BuildOutcome(pushed_step_ids=["s1"]))
    state.turn_markers.verified = verified
    return lead_deps(
        state, strategy_session=session_holding("plasmodb", "s1", "GenesByText", 132)
    )


def blame_deps() -> LeadDeps:
    return lead_deps(pipeline_state(user_prompt="Now build."))


def framing_deps() -> LeadDeps:
    deps = lead_deps(pipeline_state(user_prompt="Now build.", user_message_id=uuid4()))
    deps.state.turn_markers.framed = True
    return deps


def open_frame_deps() -> LeadDeps:
    """A turn whose frame pass left one value for the user to choose."""
    deps = framing_deps()
    deps.state.domain.open_questions = [
        OpenQuestion(question="Which gametocyte RNA-seq study?")
    ]
    study = OpenSlot(criterion_id="c_expr", param_name="dataset_url")
    deps.state.domain.operational_spec = OperationalSpec(
        goal="gametocyte genes",
        criteria=[
            Criterion(id="c_expr", text="up in gametocytes", open_params=[study])
        ],
    )
    return deps


def control_test_deps() -> LeadDeps:
    """A turn that read a control test of 7 recovered of 10 positives."""
    deps = lead_deps(
        pipeline_state(
            user_prompt="How well does it recover my controls?",
            user_message_id=uuid4(),
        ),
    )
    deps.state.turn_markers.intent_classified = True
    deps.state.turn_markers.record_control_tests(
        [
            ControlTestRun(
                tool_call_id="call_controls",
                evidence=ControlTestEvidence(
                    tested_label="Kinases",
                    wdk_step_id=440299573,
                    positive=ControlSetEvidence(
                        returned=[f"PF3D7_{n:07d}" for n in range(1133400, 1133407)],
                        not_returned=[
                            "PF3D7_0102600",
                            "PF3D7_0213400",
                            "PF3D7_0303900",
                        ],
                    ),
                ),
            )
        ]
    )
    return deps


def off_topic_deps(
    classification: IntentClassification = IntentClassification.OFF_TOPIC,
) -> LeadDeps:
    deps = lead_deps(
        pipeline_state(
            user_prompt="Write me a Python script that reverses a linked list.",
            user_message_id=uuid4(),
        ),
        intent=user_intent(classification),
    )
    deps.state.turn_markers.intent_classified = True
    return deps


def _eda_spec(*, waiting: bool = True) -> OperationalSpec:
    kinases = Criterion(id="step_k1", text="PF00069 kinases", search_name="GenesByText")
    essential = Criterion(id="c_essential", text=CRITERION, needs_analysis_on=DATASET)
    return OperationalSpec(
        goal="essential kinases",
        criteria=[kinases, essential] if waiting else [kinases],
    )


def _eda_session() -> StrategySession:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Kinases", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(
            id="step_af9d7803",
            search_name="GenesByEdaSubset",
            parameters={"eda_dataset_id": StringValue(value=DATASET)},
        ),
    )
    graph.recompute_roots()
    session.graph = graph
    return session


def eda_deps(
    *,
    waiting: bool = True,
    classification: IntentClassification = IntentClassification.EDIT_STRATEGY,
) -> LeadDeps:
    deps = lead_deps(
        pipeline_state(
            user_prompt="replace the unfiltered step with the export",
            user_message_id=uuid4(),
            domain=StrategyDomainState(operational_spec=_eda_spec(waiting=waiting)),
        ),
        intent=user_intent(classification),
        strategy_session=_eda_session(),
    )
    deps.state.turn_markers.intent_classified = True
    return deps
