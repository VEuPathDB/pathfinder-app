"""Replies and turn records the turn-contract tests share."""

from __future__ import annotations

from uuid import UUID, uuid4

from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.agents.state import CreatedGeneSet
from pathfinder.ai.graph.state import (
    CreatedControlSet,
    EnrichmentRun,
    StrategyDomainState,
)
from pathfinder.ai.lead.intent import IntentClassification
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import (
    CitedSource,
    LeadResponse,
    LeadTurnState,
    reconcile,
    turn_record,
)
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import OpenQuestion
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    DroppedCriterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
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
    "VEuPathDB refused the organism value on one step, so the build pushed two "
    "steps of three. Try again later once I re-bind that criterion."
)
CLEAN_REPLY = (
    "The planning pass stopped on its call budget with three of eight criteria "
    "bound. I am running it again on the remaining five."
)
ASKING_REPLY = (
    "The spec needs one value: which gametocyte RNA-seq study should the "
    "expression filter read? I recommend the 3D7 one."
)
ENRICHMENT_REPLY = (
    "Completed the GO enrichment (155 genes analyzed). The top terms are "
    "protein export and host cell remodeling."
)
EDA_PROSE = "The piggyBac score could not be mapped to a searchable gene field."
CONTROL_SET_CLAIM = (
    'Created the Workbench positive control set "rhoptry positives" from the '
    "strategy's rhoptry-protein step. It contains 102 genes from Toxoplasma "
    "gondii ME49."
)
GENE_SET_REPLY = (
    'Saved the 102 rhoptry-protein genes as the gene set "rhoptry positives". '
    "Do you want me to make a control set from it?"
)
LISTS_SAVED_CONTROL_SETS = (
    "You have two saved control sets on this site: 'kinase positives' with 61 "
    "genes and 'ribosomal negatives' with 84."
)
NAMES_A_CONTROL_SET_IN_A_SECOND_CLAUSE = (
    "I saved the 102 genes as a gene set; the control set is yours to ask for "
    "whenever you want one."
)
DENIES_A_CONTROL_SET = (
    "I have not created a control set: the ids are read, and nothing is saved "
    "until you name the set."
)
SAVED_GENE_SET = CreatedGeneSet(id="gs-1", name="rhoptry positives", gene_count=102)
SAVED_CONTROL_SET = CreatedControlSet(id="cs-1", name="rhoptry controls")
LISTS_SAVED_GENE_SETS = (
    "You have two saved gene sets on this site: 'kinase hits' with 61 genes "
    "and 'rhoptry positives' with 102."
)
DENIES_A_GENE_SET = (
    "I have not saved a gene set: the genes are read from the step, and "
    "nothing is stored until you name the set."
)
CLAIMS_A_GENE_SET_ENRICHMENT = (
    "I created a gene set enrichment over the 102 rhoptry-protein genes. The "
    "top terms are protein export and host cell remodeling."
)
REDIRECT = (
    "I build and check search strategies on the VEuPathDB databases, and run "
    "enrichment, EDA and exports on what they return. Ask me one of those and "
    "I will take it from there."
)
WITH_CODE = "Here you go:\n\n```python\ndef reverse(head):\n    return head\n```\n"
AN_ESSAY = "A linked list is a chain of nodes. " * 20

DATASET = "DS_70dd50fed7"
CRITERION = "essential in blood stages"
_DROP_REASON = (
    "EDA-backed criterion: the Lead builds it with open_eda_analysis, "
    "set_eda_filters, preview_eda_subset and create_eda_step."
)
FAILED_RUN = EnrichmentRun(
    task_id=UUID("0c6100d2-0000-4000-8000-0000000000a1"),
    gene_set_id="gs-requested",
    succeeded=False,
)
ANALYSED_RUN = EnrichmentRun(
    task_id=UUID("0c6100d2-0000-4000-8000-0000000000a2"),
    gene_set_id="gs-other",
    gene_set_name="WDK Strategy 214617320",
    succeeded=True,
)


def reply(
    prose: str,
    *,
    changed: bool = False,
    next_state: LeadTurnState = "await_user",
    questions: list[OpenQuestion] | None = None,
    analysed: list[str] | None = None,
    sources: list[CitedSource] | None = None,
) -> LeadResponse:
    return LeadResponse(
        prose=prose,
        next_state=next_state,
        strategy_changed=changed,
        asked_questions=list(questions or []),
        analysed_gene_set_ids=list(analysed or []),
        sources=list(sources or []),
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
        root_count=1,
    )
    return lead_deps(state)


def building_deps(*, verified: bool = True) -> LeadDeps:
    """A turn that pushed a build, checked unless the caller says otherwise."""
    state = pipeline_state(user_prompt="Add an essentiality filter.")
    state.user_message_id = uuid4()
    state.record_build(BuildOutcome(pushed_step_ids=["s1"], root_count=132))
    state.turn_markers.verified = verified
    return lead_deps(state)


def blame_deps() -> LeadDeps:
    return lead_deps(pipeline_state(user_prompt="Now build."))


def framing_deps() -> LeadDeps:
    deps = lead_deps(pipeline_state(user_prompt="Now build.", user_message_id=uuid4()))
    deps.state.turn_markers.framed = True
    return deps


def enrichment_deps(*runs: EnrichmentRun) -> LeadDeps:
    deps = lead_deps(
        pipeline_state(
            user_prompt="Run GO enrichment on my gametocyte set.",
            user_message_id=uuid4(),
        ),
    )
    deps.state.turn_markers.enrichment_runs = list(runs)
    return deps


def control_source_deps(
    *,
    saved_gene_set: bool = True,
    wrote_control_set: bool = False,
) -> LeadDeps:
    """A turn that read a step's ids and saved them as a workbench gene set."""
    deps = lead_deps(
        pipeline_state(
            site_id="toxodb",
            user_prompt=(
                "Build a positive control set from the genes this strategy's "
                "rhoptry step holds, and call it rhoptry positives."
            ),
            user_message_id=uuid4(),
        ),
    )
    if saved_gene_set:
        deps.state.turn_markers.record_gene_set(SAVED_GENE_SET)
    if wrote_control_set:
        deps.state.turn_markers.record_control_set(SAVED_CONTROL_SET)
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


def _eda_spec(*, dropped: bool = True) -> OperationalSpec:
    return OperationalSpec(
        goal="essential kinases",
        criteria=[
            Criterion(id="step_k1", text="PF00069 kinases", search_name="GenesByText"),
        ],
        dropped=[
            DroppedCriterion(
                text=CRITERION, reason=_DROP_REASON, eda_dataset_id=DATASET
            ),
        ]
        if dropped
        else [],
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
    dropped: bool = True,
    classification: IntentClassification = IntentClassification.EDIT_STRATEGY,
) -> LeadDeps:
    deps = lead_deps(
        pipeline_state(
            user_prompt="replace the unfiltered step with the export",
            user_message_id=uuid4(),
            domain=StrategyDomainState(operational_spec=_eda_spec(dropped=dropped)),
        ),
        intent=user_intent(classification),
        strategy_session=_eda_session(),
    )
    deps.state.turn_markers.intent_classified = True
    return deps
