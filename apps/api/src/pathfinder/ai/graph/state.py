from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from typing import Literal
from uuid import UUID

from assistant_core.graph.turn_state import TurnState
from assistant_core.memory.schemas import MemoryEntryDraft
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict, Field

from pathfinder.ai.agents.state import CreatedGeneSet, SearchOverview
from pathfinder.ai.lead.intent import (
    REQUEST_INTENTS,
    IntentClassification,
    UserIntent,
)
from pathfinder.domain.eda_parts import EdaFilterSheetEntry, OpenEdaSheet
from pathfinder.domain.eda_thread import (
    EdaAnalysisFacts,
    EdaExport,
    OpenEdaAnalysis,
)
from pathfinder.domain.strategy.build_outcome import (
    BuildOutcome,
)
from pathfinder.domain.strategy.combination_check import combination_terms_overlap
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OpenQuestion,
    message_states_constraint,
    standing_recommendations,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.staleness import StaleBuild

PhaseName = Literal[
    "frame",
    "build",
    "verification",
]

PHASE_NAMES: tuple[PhaseName, ...] = (
    "frame",
    "build",
    "verification",
)


class PhaseDisposition(StrEnum):
    AWAITING_USER = "awaiting_user"
    HANDOFF = "handoff"
    DONE = "done"


class FailureCause(StrEnum):
    """Typed cause of a phase's exit, surfaced to the LLM supervisor."""

    VOCAB_REJECTED = "vocab_rejected"
    AMBIGUOUS_INTENT = "ambiguous_intent"
    SEARCH_INVALID = "search_invalid"
    PARTIAL_BUILD = "partial_build"
    UNRESOLVED_SLOTS = "unresolved_slots"
    TRANSIENT_ERROR = "transient_error"
    STRUCTURE_VIOLATION = "structure_violation"


class ConstraintCheck(CamelModel):
    label: str
    requested: str
    realized: str
    honored: bool
    note: str = ""


class VerificationDigest(CamelModel):
    disposition: PhaseDisposition = Field(
        description=(
            "Control-flow signal: 'done' = investigation is complete; "
            "'awaiting_user' = the turn ends; 'handoff' = transition to "
            "the next sub-agent."
        ),
    )
    prose: str = Field(
        min_length=1,
        max_length=4000,
        description="User-facing assistant message shown in the chat thread.",
    )
    reason: str = Field(
        min_length=1,
        max_length=280,
        description="Short routing explanation shown on the orchestrator card.",
    )
    handoff_to: PhaseName | None = None
    failure_cause: FailureCause | None = Field(default=None)
    note_refs: list[str] = Field(default_factory=list, max_length=10)
    success: bool = Field(
        description=(
            "True if the strategy answered the user's question: sample "
            "records and result sizes look right, control tests passed."
        ),
    )
    key_findings: list[str] = Field(default_factory=list, max_length=10)
    caveats: list[str] = Field(default_factory=list, max_length=10)
    constraint_report: list[ConstraintCheck] = Field(
        default_factory=list, max_length=12
    )
    remember: list[MemoryEntryDraft] = Field(
        default_factory=list,
        max_length=5,
        description=(
            "Durable findings worth a later turn, each with a recall-friendly "
            'name such as "P. falciparum kinome size", counts or identifiers '
            "in its content, and tags naming an organism, a technique or a "
            "dataset. The site id is added automatically."
        ),
    )


class ZeroResultStep(CamelModel):
    """A search that came back empty on some build of this thread."""

    search_name: str
    criterion_text: str = ""


class EnrichmentRun(CamelModel):
    """One enrichment a durable task answered, and what it named.

    A run that failed names the set it was asked for; a run that finished
    names the set the worker reports it analysed.
    """

    task_id: UUID
    gene_set_id: str
    gene_set_name: str = ""
    succeeded: bool = False


class TurnMarkers(CamelModel):
    """What the Lead already did for one user message.

    The record belongs to the message it names. A turn answering a different
    message starts from an empty one, so nothing an earlier message unlocked
    is still unlocked.
    """

    message_id: UUID | None = None
    intent_classified: bool = False
    framed: bool = False
    built: bool = False
    verified: bool = False
    verification_dispatched: bool = False
    verification_nudged: bool = False
    # The EDA cut this turn exported, which the turn's case records.
    eda_export: EdaExport | None = None
    # Every enrichment answered under this message, in the order the workers
    # answered them. A reply reads it to say which set an analysis ran on.
    enrichment_runs: list[EnrichmentRun] = Field(default_factory=list)

    def record_enrichment_runs(self, runs: Iterable[EnrichmentRun]) -> None:
        """Add each answered enrichment once, keyed by its task."""
        known = {run.task_id for run in self.enrichment_runs}
        for run in runs:
            if run.task_id in known:
                continue
            known.add(run.task_id)
            self.enrichment_runs.append(run)


class StrategyDomainState(BaseModel):
    """What the investigation knows: the framed spec, the searches it saw,
    the last build and its verification."""

    # A conversation saved by an earlier build may carry a field this build
    # dropped; the value is discarded and the rest of the state is rebuilt.
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    user_intent: UserIntent | None = None
    turn_markers: TurnMarkers = Field(default_factory=TurnMarkers)
    lead_next_state: Literal["await_user", "complete"] | None = None
    operational_spec: OperationalSpec | None = None
    # The spec as the turn found it, written by the pre-turn hook. An edit's
    # dispositions are checked against this and never against the model's memory.
    spec_before_turn: OperationalSpec | None = None
    discovered_searches: dict[str, SearchOverview] = Field(default_factory=dict)
    verification_digest: VerificationDigest | None = None
    last_build_outcome: BuildOutcome | None = None
    # Recomputed at the start of every Lead turn by comparing the live
    # strategy against ``last_build_outcome``. Never persisted: an edit that
    # was stale last turn is not stale after the next build.
    stale_build: StaleBuild | None = None
    created_gene_sets: list[CreatedGeneSet] = Field(default_factory=list)
    # The EDA filter sheet the thread holds open, and the study it describes.
    open_eda_sheet: OpenEdaSheet | None = None
    # The analysis-state card the thread last showed. A tool emits the card
    # again only when the state differs from this.
    eda_analysis: EdaAnalysisFacts | None = None
    # The analysis the thread holds open, read from the binding at turn entry.
    # Never persisted: another surface can close or replace it between turns.
    open_eda_analysis: OpenEdaAnalysis | None = None
    # Every requirement the thread has stated, oldest first. A clarification
    # adds to this list; only a message that abandons the request clears it.
    requirements: list[Constraint] = Field(default_factory=list)
    # What the thread asked the user and has not heard back on, with the value
    # each question recommended.
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    # The recommended values the thread's requirements leave standing. A
    # requirement on the same dimension replaces one.
    recommendations: list[Constraint] = Field(default_factory=list)
    # The request the thread is answering, as the user wrote it.
    original_request: str = ""
    # What moved on the thread since its last answer, as the pre-turn hook
    # rendered it. Empty when nothing moved.
    turn_briefing: str = ""
    # Every search that emptied a step on some build of this thread. A later
    # build that fills one of them is the recovery a case records.
    zero_result_history: list[ZeroResultStep] = Field(default_factory=list)

    @property
    def has_strategy(self) -> bool:
        """Whether this thread already describes or holds a strategy."""
        spec = self.operational_spec
        return bool(spec and spec.criteria) or self.last_build_outcome is not None

    def continues_the_request(self, intent: UserIntent) -> bool:
        """Whether this message carries the thread's request on.

        Only a question that names the dimension it decides narrows the match:
        a message answering one of those, or stating nothing of its own,
        continues the request. A question that names none could be the one this
        message answers, and where no question was recorded a thread that ended
        waiting on the user keeps what it states.
        """
        asked = [q for q in self.open_questions if q.decides_a_dimension]
        if len(asked) != len(self.open_questions):
            return True
        if not asked:
            return self.lead_next_state == "await_user" and bool(self.requirements)
        dimensions = {question.dimension for question in asked}
        return not intent.explicit_constraints or any(
            c.kind in dimensions for c in intent.explicit_constraints
        )

    def _attributed(
        self, constraints: Iterable[Constraint], message: str
    ) -> list[Constraint]:
        """Each stated requirement, marked by who the message says stated it.

        A value the message carries is the user's word. A value only the
        classifier composed is an assumption: it is surfaced, and it gates
        nothing. A value the user already stated on this thread stays theirs.
        """
        theirs = {
            c.requested_value.casefold()
            for c in self.requirements
            if c.source is ConstraintSource.USER_EXPLICIT
        }
        attributed: list[Constraint] = []
        for constraint in constraints:
            stated = (
                message_states_constraint(message, constraint)
                or constraint.requested_value.casefold() in theirs
            )
            attributed.append(
                constraint.model_copy(
                    update={
                        "source": ConstraintSource.USER_EXPLICIT
                        if stated
                        else ConstraintSource.ASSUMED,
                        "hard": constraint.hard and stated,
                    },
                ),
            )
        return attributed

    def record_intent(self, intent: UserIntent, *, request_text: str) -> None:
        """Take this turn's requirements and the request they belong to.

        The questions the thread asked are answered by this message, whatever
        it answers, so nothing waits on them after it.
        """
        if (
            intent.classification is IntentClassification.NEW_STRATEGY
            and not self.has_strategy
            and not self.continues_the_request(intent)
        ):
            self.requirements = []
            self.recommendations = []
            self.original_request = ""
        self.record_requirements(
            self._attributed(intent.explicit_constraints, request_text),
        )
        self.record_recommendations()
        self.open_questions = []
        if not self.original_request and intent.classification in REQUEST_INTENTS:
            self.original_request = request_text

    def record_questions(self, questions: Iterable[OpenQuestion]) -> None:
        """Add each question the thread has not asked already."""
        asked = {question.question for question in self.open_questions}
        for question in questions:
            if question.question in asked:
                continue
            asked.add(question.question)
            self.open_questions.append(question)

    def record_recommendations(self) -> None:
        """Keep the recommendations the thread's requirements leave standing.

        An accepted recommendation is recorded once, so a later reply that asks
        something else does not drop it.
        """
        replaced = {c.kind for c in self.requirements}
        held = [c for c in self.recommendations if c.kind not in replaced]
        seen = {(c.kind, c.requested_value) for c in held}
        for offered in standing_recommendations(self.open_questions, self.requirements):
            key = (offered.kind, offered.requested_value)
            if key in seen:
                continue
            seen.add(key)
            held.append(offered)
        self.recommendations = held

    def record_requirements(self, constraints: Iterable[Constraint]) -> None:
        """Add each requirement the thread has not stated already.

        Two requirements are the same when they hold the same value on the same
        dimension, so a restated one is not a second requirement. A new
        combination over the same criteria replaces the old one, so a changed
        mind never leaves two statements no tree can satisfy together.
        """
        seen = {(c.kind, c.requested_value) for c in self.requirements}
        for constraint in constraints:
            key = (constraint.kind, constraint.requested_value)
            if key in seen:
                continue
            if constraint.kind is ConstraintKind.COMBINATION:
                self.requirements = [
                    held
                    for held in self.requirements
                    if held.kind is not ConstraintKind.COMBINATION
                    or not combination_terms_overlap(
                        held.requested_value, constraint.requested_value
                    )
                ]
            seen.add(key)
            self.requirements.append(constraint)

    def markers_for(self, message_id: UUID | None) -> TurnMarkers:
        """This turn's markers. The record rotates on a new user message."""
        if self.turn_markers.message_id != message_id:
            self.turn_markers = TurnMarkers(message_id=message_id)
        return self.turn_markers

    def record_zero_results(self, outcome: BuildOutcome) -> None:
        """Add each search this build emptied, once per search."""
        spec = self.operational_spec
        criteria = spec.criteria if spec is not None else []
        text_of = {c.search_name: c.text for c in criteria if c.search_name}
        known = {entry.search_name for entry in self.zero_result_history}
        for node in outcome.node_results:
            if node.status != "zero" or node.search_name in known:
                continue
            known.add(node.search_name)
            self.zero_result_history.append(
                ZeroResultStep(
                    search_name=node.search_name,
                    criterion_text=text_of.get(node.search_name, ""),
                ),
            )

    def record_criterion(self, criterion: Criterion) -> None:
        """State one criterion on the framed spec, keyed by the step it names.

        A thread that framed no spec states nothing about its strategy, so
        there is nothing to record on.
        """
        spec = self.operational_spec
        if spec is None:
            return
        spec.criteria = [c for c in spec.criteria if c.id != criterion.id]
        spec.criteria.append(criterion)

    def pin_eda_sheet(
        self, dataset_id: str, entries: list[EdaFilterSheetEntry]
    ) -> None:
        """Open the filter sheet for a study, replacing anything it holds."""
        self.open_eda_sheet = OpenEdaSheet(dataset_id=dataset_id, entries=entries)

    def close_eda_sheet(self) -> None:
        """Drop the sheet whose subset is now applied."""
        self.open_eda_sheet = None

    def close_eda_sheet_of_another_study(self, dataset_id: str) -> None:
        """Drop the sheet when the conversation opens a different study.

        A study the conversation no longer has open cannot be filtered, so its
        sheet describes nothing the model can act on.
        """
        sheet = self.open_eda_sheet
        if sheet is not None and sheet.dataset_id != dataset_id:
            self.open_eda_sheet = None


class PipelineState(TurnState):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="ignore")

    domain: StrategyDomainState = Field(default_factory=StrategyDomainState)

    @property
    def turn_markers(self) -> TurnMarkers:
        """What the Lead already did for the message this turn answers."""
        return self.domain.markers_for(self.user_message_id)

    def record_build(self, outcome: BuildOutcome) -> None:
        """Take the build this turn produced, and the searches it emptied."""
        self.domain.last_build_outcome = outcome
        self.domain.record_zero_results(outcome)
        self.turn_markers.built = True
