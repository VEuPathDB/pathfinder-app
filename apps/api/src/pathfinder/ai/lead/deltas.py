from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.phase_stop import PhaseStop
from pathfinder.ai.tools.standalone.graph_helpers import counted_noun
from pathfinder.domain.omitted_from_input import OmittedFromInput
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import Constraint
from pathfinder.domain.strategy.named_groups import GroupScope
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.questions import (
    OpenQuestion,
    SlotQuestion,
)
from pathfinder.domain.strategy.requirement_reports import (
    RecordTypeRole,
    ReportedRequirement,
    RequirementReport,
    numbered_requirements,
    stated_numbers,
)
from pathfinder.domain.strategy.spec_diff import CriterionChange, SpecDiff
from pathfinder.domain.strategy.step_words import AddedSearch
from pathfinder.domain.turn_facts import UnsavedSetFact

_ADDED_SEARCHES = (
    "The search each step this turn added runs, by its name on the site, the "
    "words it stands for, and why it was chosen over the searches the catalog "
    "answered. The reply names every one and gives its reason beside the name."
)


PassGapKind = Literal[
    "reading_left_out",
    "question_without_readings",
    "readings_name_no_requirement",
    "report_dropped",
    "question_decides_nothing",
    "questions_bind_nothing",
    "every_genome_unasked",
    "group_genomes_left_out",
    "group_scope_missing",
    "group_scope_exception_unknown",
    "missing_after_refusal",
    "record_role_missing",
    "record_type_unknown",
]


class PassGap(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: PassGapKind
    sentence: str


class FrameResult(CamelModel):
    """FRAME sub-agent output. The OperationalSpec is committed to agent_state
    via tools (not re-typed here); this delta is a light summary + disposition."""

    summary: str = ""
    disposition: Literal["spec_ready", "needs_user", "needs_research"] = "spec_ready"
    open_questions: list[SlotQuestion] = Field(
        default_factory=list,
        description=(
            "One entry per open slot only the user can decide, each naming "
            "the dimension its answer states, the value you recommend, the "
            "`criterion_id` and `param_name` of the slot, and in `options` up "
            "to 8 values the sheet you read offers for it: its facets or its "
            "vocabulary. Each option sets that parameter to its value. A "
            "free-text or range parameter offers two or three `readings` "
            "instead, each a label with its numbers, the value it binds and "
            "its caveat. A value is the expression or value the parameter "
            "takes, which the site builds as written, never a description in "
            "words. When requirements the researcher stated are listed, the "
            "question names in its own `requirements` the keys (R1, R2) of "
            "those its readings approximate; with no list, it names none. The "
            "Lead asks it on the question card with those options."
        ),
    )
    requirement_problems: list[RequirementReport] = Field(
        default_factory=list,
        exclude=True,
        description=(
            "One entry for each requirement, from 'Requirements the researcher "
            "stated' in your instructions, that the strategy does not answer as "
            "asked. A requirement a bound search answers as asked is never "
            "listed. Empty when every requirement is answered."
        ),
    )
    record_types: list[RecordTypeRole] = Field(
        default_factory=list,
        exclude=True,
        description=(
            "One entry for each requirement, from 'Requirements the researcher "
            "stated' in your instructions, that names a record type: whether "
            "the result is those records, or the tree passes through them."
        ),
    )
    group_scopes: list[GroupScope] = Field(
        default_factory=list,
        exclude=True,
        description=(
            "One entry for each genus, species or clade whose genomes the units "
            "of a phyletic expression name more than one of: whether the "
            "request means the whole taxon, or exactly the units written."
        ),
    )
    # The reports with the held words in place of each number. The dispatch
    # sets it, so FRAME's schema omits it and the Lead reads it.
    reported: Annotated[list[ReportedRequirement], OmittedFromInput] = Field(
        default_factory=list
    )
    # What the pass did to each criterion the workspace held: kept only when
    # its wire values did not move. The dispatch derives it from the two
    # specs, so FRAME's schema omits it.
    changes: Annotated[list[CriterionChange], OmittedFromInput] = Field(
        default_factory=list
    )
    # The open questions as the question card asks them. The dispatch sets it
    # from the recorded questions, so FRAME's schema omits it.
    card_questions: Annotated[list[CardQuestion], OmittedFromInput] = Field(
        default_factory=list
    )

    gaps: Annotated[list[PassGap], OmittedFromInput] = Field(default_factory=list)

    def with_gaps(self, gaps: Sequence[PassGap]) -> FrameResult:
        return self.model_copy(update={"gaps": [*self.gaps, *gaps]})

    def with_gap(self, kind: PassGapKind, sentence: str) -> FrameResult:
        return self.with_gaps([PassGap(kind=kind, sentence=sentence)])

    @property
    def undecided_questions(self) -> list[str]:
        if self.disposition != "needs_user":
            return []
        return [q.question for q in self.open_questions if not q.decides_a_dimension]

    def questions(
        self,
        spec: OperationalSpec | None = None,
        requirements: Sequence[Constraint] = (),
    ) -> list[OpenQuestion]:
        """The open questions, each option typed by what answering it binds.

        ``spec`` holds the criteria the questions set, which name each
        parameter and hold the counts measured at the offered values. A
        question whose offered values bind one value offers no choice, so it
        is not asked.
        """
        by_id = {c.id: c for c in spec.criteria} if spec is not None else {}
        noun = counted_noun(None if spec is None else spec.record_type)
        numbered = numbered_requirements(requirements)
        return [
            q.typed(
                by_id.get(q.criterion_id),
                noun=noun,
                replaces=[numbered[n].key for n in q.requirements if n in numbered],
                stated=bool(stated_numbers(requirements)),
            )
            for q in self.open_questions
            if q.offers_a_choice(by_id.get(q.criterion_id))
        ]


_UNSAVED_GENE_SET = (
    "Set when the result holds more genes than a gene set holds: no gene set "
    "was saved from it. The reply says so and never says the result is saved."
)


class ExecuteDelta(CamelModel):
    """Declarative BUILD output. No LLM ran; this is the build result."""

    outcome: BuildOutcome
    added_searches: list[AddedSearch] = Field(
        default_factory=list, description=_ADDED_SEARCHES
    )
    unsaved_gene_set: UnsavedSetFact | None = Field(
        default=None, description=_UNSAVED_GENE_SET
    )


class EditDelta(CamelModel):
    """What an edit turn did to the strategy that already existed.

    ``preserved_step_ids`` are the steps the edit left alone: their WDK ids and
    their values are the ones the previous turn reported.
    """

    diff: SpecDiff
    # ``unbound``: every framing pass of the edit was refused, and the summary
    # says why; nothing was applied.
    disposition: Literal["applied", "needs_user", "unbound"] = "applied"
    summary: str = ""
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    # The open questions as the question card asks them, option by option.
    card_questions: list[CardQuestion] = Field(default_factory=list)
    # What the framing pass reported about a requirement the edit does not answer.
    reported: list[ReportedRequirement] = Field(default_factory=list)
    gaps: list[PassGap] = Field(default_factory=list)
    description: str = ""
    operations_applied: int = 0
    added_step_ids: list[str] = Field(
        default_factory=list,
        description=(
            "The criteria this edit built a step for, which is what the diff "
            "counts as added: the diff is measured against the spec the "
            "strategy answers to, so a criterion framed on an earlier turn and "
            "built here reads as added in both."
        ),
    )
    added_searches: list[AddedSearch] = Field(
        default_factory=list, description=_ADDED_SEARCHES
    )
    unsaved_gene_set: UnsavedSetFact | None = Field(
        default=None, description=_UNSAVED_GENE_SET
    )
    preserved_step_ids: list[str] = Field(default_factory=list)
    dropped_step_ids: list[str] = Field(default_factory=list)
    pending_step_ids: list[str] = Field(
        default_factory=list,
        description=(
            "The criteria a pass that ended in a question moved in the plan and "
            "no push wrote: the strategy still runs their earlier values, so no "
            "sentence calls them changed."
        ),
    )
    failed_step_ids: list[str] = Field(default_factory=list)


class RecoveryDelta(CamelModel):
    """Execution-recovery sub-agent output (only invoked when build fails).

    The agent emits only the light fields; the resulting ``BuildOutcome`` is
    re-derived by re-syncing the strategy (the agent re-typing the full outcome
    object fumbled ``counts`` and caused a think-loop)."""

    actions_taken: list[str] = Field(default_factory=list)
    follow_up_needed: bool = False


_CARD_RULE = (
    "The strategy changes only through a card this turn: offer any change "
    "with propose_changes showing the count before and after it, or report "
    "the finding and ask."
)


class VerificationDelta(CamelModel):
    """Verification sub-agent output."""

    digest: VerificationDigest

    @computed
    def next_step(self) -> str | None:
        """How the strategy may change after this check, or None when the build fixes it."""
        return None if self.digest.blames_the_tree else _CARD_RULE


class VerificationStopped(CamelModel):
    """A check that ended before it returned a digest. It records no verdict
    and no evidence card, so the strategy stays unverified."""

    stop: PhaseStop | None
    summary: str
