from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, model_validator

from strategist.ai.graph.state import VerificationDigest
from strategist.ai.lead.card_question import CardQuestion
from strategist.ai.lead.phase_stop import PhaseStop, stop_phrase
from strategist.ai.tools.standalone.graph_helpers import counted_noun
from strategist.domain.omitted_from_input import OmittedFromInput
from strategist.domain.pending_plan import PendingPlan
from strategist.domain.strategy.build_outcome import BuildOutcome
from strategist.domain.strategy.chosen_reading import ChosenReading
from strategist.domain.strategy.constraints import Constraint
from strategist.domain.strategy.named_groups import GroupScope
from strategist.domain.strategy.operational_spec import OperationalSpec
from strategist.domain.strategy.questions import (
    OpenQuestion,
    SlotQuestion,
)
from strategist.domain.strategy.requirement_reports import (
    ReportedRequirement,
    RequirementReport,
    numbered_requirements,
    stated_numbers,
)
from strategist.domain.strategy.spec_diff import CriterionChange, SpecDiff
from strategist.domain.strategy.step_words import AddedSearch
from strategist.domain.turn_facts import UnsavedSetFact

_ADDED_SEARCHES = (
    "The search each step this turn added runs, by its name on the site, the "
    "words it stands for, and why it was chosen over the searches the catalog "
    "answered. The reply names every one and gives its reason beside the name."
)


_NO_READINGS: Mapping[str, str] = MappingProxyType({})
_NOTHING_APPLIED = "Nothing was applied: the strategy is unchanged."
_UNDONE = "The strategy is back to the revision before the last change."
_MOVED_NOTHING = "an edit that applied nothing carries no operation and no diff"

PassGapKind = Literal[
    "absence_not_read",
    "reading_left_out",
    "question_without_readings",
    "readings_name_no_requirement",
    "reading_keys_unknown",
    "report_dropped",
    "question_decides_nothing",
    "questions_bind_nothing",
    "expression_handle_unknown",
    "group_genomes_left_out",
    "group_scope_missing",
    "group_scope_exception_unknown",
    "missing_after_refusal",
    "organism_step_missing",
    "record_type_unknown",
    "structure_names_unbound",
    "option_not_a_value",
    "refusal_spent",
    "pass_stopped",
]


class PassGap(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: PassGapKind
    sentence: str


class FrameResult(CamelModel):
    """FRAME sub-agent output. The OperationalSpec is committed to agent_state
    via tools (not re-typed here); this delta is a disposition and FRAME's notes,
    which the Lead reads only as a pending plan."""

    notes: str = Field(
        default="",
        exclude=True,
        description=(
            "What the Lead must tell the researcher about the plan you drafted "
            "that no other field states. Nothing you draft is applied."
        ),
    )
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
            "those its readings approximate; with no list, it names none. "
            "Every question about a held requirement names that requirement's "
            "key in `requirements` too, so its drop and keep options join that "
            "question and the card asks one question per requirement. The "
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
    group_scopes: list[GroupScope] = Field(
        default_factory=list,
        exclude=True,
        description=(
            "One entry for each genus, species or clade whose genomes the units "
            "of a phyletic expression name more than one of: whether the "
            "request means the whole taxon, or exactly the units written."
        ),
    )
    chosen_reading: ChosenReading | None = Field(
        default=None,
        description=(
            "Only when the request reads two or more ways, the readings would "
            "build different strategies, and you built one without asking: "
            "the reading you built and each other reading. The Lead's reply "
            "names every one of them. None when the request reads one way or "
            "you ask which reading it means."
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
    route: Annotated[str, OmittedFromInput] = ""

    @computed
    def pending_plan(self) -> PendingPlan | None:
        if not self.notes:
            return None
        waits_on = "answer" if self.disposition == "needs_user" else "build"
        return PendingPlan(text=self.notes, waits_on=waits_on)

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
        readings: Mapping[str, str] = _NO_READINGS,
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
                replaces=[numbered[n].id for n in q.requirements if n in numbered],
                stated=bool(stated_numbers(requirements)),
                readings=readings,
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
    # ``unbound``: every framing pass of the edit was refused, and ``refusal``
    # says why; nothing was applied.
    disposition: Literal["applied", "needs_user", "unbound"] = "applied"
    refusal: str = ""
    route: str = ""
    undone: bool = False
    pending_plan: PendingPlan | None = None
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

    @model_validator(mode="after")
    def _nothing_applied_moves_nothing(self) -> EditDelta:
        if self.disposition != "applied" and (
            self.operations_applied or self.diff.changes
        ):
            raise ValueError(_MOVED_NOTHING)
        return self

    @computed
    def summary(self) -> str:
        if self.disposition != "applied":
            return _NOTHING_APPLIED
        return _UNDONE if self.undone else ""


class RecoveryDelta(CamelModel):
    """Execution-recovery sub-agent output (only invoked when build fails).

    The agent emits only the light fields; the resulting ``BuildOutcome`` is
    re-derived by re-syncing the strategy (the agent re-typing the full outcome
    object fumbled ``counts`` and caused a think-loop)."""

    actions_taken: list[str] = Field(default_factory=list)
    follow_up_needed: bool = False


_CARD_RULE = (
    "The strategy changes only through a card this turn: offer any change "
    "on a card that shows the count before and after it, or report the "
    "finding and ask."
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

    @computed
    def summary(self) -> str:
        why = (
            "stopped before it finished"
            if self.stop is None
            else stop_phrase(self.stop)
        )
        return (
            f"VERIFY {why}, so it recorded no verdict and the strategy is not "
            "verified. Tell the user the check did not finish and why, and ask "
            "whether to run it again."
        )
