from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from enum import StrEnum
from typing import Literal
from uuid import UUID

from assistant_core.graph.turn_state import TurnState
from assistant_core.memory.schemas import MemoryEntryDraft
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.strategy import StrategyAst

from pathfinder.ai.agents.state import CreatedGeneSet, SearchOverview
from pathfinder.ai.graph.turn_records import (
    AnsweredQuestions,
    TurnMarkers,
    ZeroResultStep,
)
from pathfinder.ai.lead.intent import REQUEST_INTENTS, UserIntent
from pathfinder.ai.lead.proposal import DeclinedProposal
from pathfinder.domain.eda_parts import EdaFilterSheetEntry, OpenEdaSheet
from pathfinder.domain.eda_thread import (
    EdaAnalysisFacts,
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
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    renumber_criteria,
)
from pathfinder.domain.strategy.revision import strategy_revision
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
    pending_checks: list[str] = Field(
        default_factory=list,
        description=(
            "The study steps whose analysis the site did not describe, so their "
            "check could not run. The runtime sets it from the strategy and "
            "replaces anything written here."
        ),
    )
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

    @property
    def passed(self) -> bool:
        """True when the check succeeded and no step's check is pending."""
        return self.success and not self.pending_checks


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
    # The last spec the strategy was made to answer to, and the tree it held at
    # that moment. An edit is planned against the first; everything between the
    # second and the live tree was written outside this thread.
    answered_spec: OperationalSpec | None = None
    answered_graph: StrategyAst | None = None
    # The spec the turn entered with, written by the pre-turn hook and re-keyed
    # by a build onto the steps it made. The ledger diffs the turn against it.
    spec_before_turn: OperationalSpec | None = None
    # The committed spec as the running dispatch found it. The pass states its
    # dispositions against it, and a refusal puts it back.
    spec_before_dispatch: OperationalSpec | None = None
    discovered_searches: dict[str, SearchOverview] = Field(default_factory=dict)
    verification_digest: VerificationDigest | None = None
    # The revision of the strategy the digest judged. The digest is the verdict
    # only while the strategy holds that revision.
    verified_revision: str = ""
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
    # The last proposal the researcher declined. A later bare yes does not
    # accept it: the offer is made again on a new card.
    declined_proposal: DeclinedProposal | None = None

    def set_the_request_aside(self) -> None:
        """Forget the request the thread answered and everything stated for it."""
        self.operational_spec = None
        self.requirements = []
        self.recommendations = []
        self.open_questions = []
        self.original_request = ""
        self.last_build_outcome = None
        self.stale_build = None

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

    def take_a_new_request(self, *, strategy_has_steps: bool) -> None:
        """Drop the questions asked about the request a new one sets aside.

        The answer this message gave them goes too. Over a thread whose
        strategy holds no step the new request also replaces the old one.
        """
        self.open_questions = []
        self.turn_markers.answered = None
        if not strategy_has_steps:
            self.set_the_request_aside()

    def record_intent(self, intent: UserIntent, *, request_text: str) -> None:
        """Take this turn's requirements and the request they belong to."""
        self.record_requirements(
            self._attributed(intent.explicit_constraints, request_text),
        )
        self.record_recommendations()
        if not self.original_request and intent.classification in REQUEST_INTENTS:
            self.original_request = request_text

    def answer_open_questions(self, answer: str, *, on_card: bool = False) -> None:
        """Close every question open now, whatever the answer says.

        A card answers the questions a pass asked under this same message.
        """
        self._answer(self.open_questions, answer, on_card=on_card)

    def answer_the_questions_at_arrival(self, answer: str) -> None:
        """Close the questions this message found open, and no later one."""
        arrived = set(self.turn_markers.questions_at_arrival)
        self._answer([q for q in self.open_questions if q.question in arrived], answer)

    def _answer(
        self, questions: list[OpenQuestion], answer: str, *, on_card: bool = False
    ) -> None:
        # A later answer under the same message replaces the record, because
        # the draft already holds what the earlier one decided.
        if not questions:
            return
        self.turn_markers.answered = AnsweredQuestions(
            questions=questions, answer=answer, on_card=on_card
        )
        self.open_questions = [q for q in self.open_questions if q not in questions]

    def record_questions(self, questions: Iterable[OpenQuestion]) -> None:
        """Add each question the thread has not asked already."""
        for question in questions:
            if question.question not in {q.question for q in self.open_questions}:
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
            self.turn_markers = TurnMarkers(
                message_id=message_id,
                questions_at_arrival=[q.question for q in self.open_questions],
            )
        return self.turn_markers

    def record_verdict(self, digest: VerificationDigest, *, revision: str) -> None:
        """Keep a check's digest with the revision of the strategy it judged."""
        self.verification_digest = digest
        self.verified_revision = revision

    def verdict_of_the_strategy(self) -> VerificationDigest | None:
        """The digest of the last check, while the strategy is the one it judged.

        ``answered_graph`` is the tree the strategy holds after every write of
        this thread and every refresh, so its revision is the live one.
        """
        if self.verified_revision != strategy_revision(self.answered_graph):
            return None
        return self.verification_digest

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

    def restate_every_record(
        self,
        step_id_by_criterion: Mapping[str, str],
        restated: Callable[[OperationalSpec], OperationalSpec],
    ) -> None:
        """Move every spec the turn holds onto the steps that bound its criteria.

        The plan, the answer and the dispatch record take ``restated``. The
        turn's entry record is only re-keyed, so the ledger still reads what
        this turn did to the criteria it entered with.
        """
        named = set(step_id_by_criterion)

        def _one(
            spec: OperationalSpec | None,
            restate: Callable[[OperationalSpec], OperationalSpec],
        ) -> OperationalSpec | None:
            if spec is None or named.isdisjoint(c.id for c in spec.criteria):
                return spec
            return restate(spec)

        def _rekeyed(spec: OperationalSpec) -> OperationalSpec:
            return renumber_criteria(spec, dict(step_id_by_criterion))

        self.operational_spec = _one(self.operational_spec, restated)
        self.answered_spec = _one(self.answered_spec, restated)
        self.spec_before_dispatch = _one(self.spec_before_dispatch, restated)
        self.spec_before_turn = _one(self.spec_before_turn, _rekeyed)

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

    @property
    def turn_verdict(self) -> VerificationDigest | None:
        """The verdict on the strategy as it stands, or None."""
        return self.domain.verdict_of_the_strategy()

    @property
    def request_the_thread_answers(self) -> str:
        """The request the thread answers, or this message when none is recorded."""
        return self.domain.original_request or self.user_prompt

    def record_resync(self, outcome: BuildOutcome) -> None:
        """Take the counts a sync read, and the searches it found empty.

        The counts are read from the strategy as it stands, so the staleness
        measured against the earlier build no longer applies.
        """
        self.domain.last_build_outcome = outcome
        self.domain.stale_build = None
        self.domain.record_zero_results(outcome)

    def record_build(self, outcome: BuildOutcome) -> None:
        """Take the build this turn produced, and the searches it emptied."""
        self.record_resync(outcome)
        self.turn_markers.built = True
