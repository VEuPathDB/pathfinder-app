"""The facts a turn shows beside the Lead's reply: the strategy's steps and
values, what the check measured, and what the turn saved or was refused."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, ValidationInfo, field_validator

from pathfinder.domain.caveats import Caveat, Gap, PhraseCaveat, SampleCaveat
from pathfinder.domain.comparison_facts import ComparisonFact
from pathfinder.domain.control_result_facts import ControlResultFact
from pathfinder.domain.count_words import counted
from pathfinder.domain.evidence import ColumnFit, GeneFit
from pathfinder.domain.last_change import LastChange
from pathfinder.domain.statistic_facts import StatisticFact
from pathfinder.domain.strategy.operational_spec import ValueSource
from pathfinder.domain.value_caveats import (
    AssumedValueCaveat,
    ChoiceCaveat,
    UnmeasuredValueCaveat,
    ValueCaveat,
)

type SavedKind = Literal["gene_set", "control_set"]
type RetiredState = Literal["withdrawn", "replaced"]


def _counted(count: int | None, noun: str) -> str:
    return "count not available" if count is None else counted(count, noun)


def _with_before(count: int | None, before: int | None, noun: str) -> str:
    if before is None:
        return _counted(count, noun)
    return f"{_counted(count, noun)}, {_counted(before, noun)} before this turn's edit"


class ParameterFact(CamelModel):
    """One bound value of a step and who set it. ``name`` is the wire name the
    facts part does not show; ``notes`` are a default or chosen value's
    measurement clauses and a card value's option label."""

    model_config = ConfigDict(frozen=True)

    name: str
    display_name: str
    value: str
    label: str = ""
    source: ValueSource
    notes: list[str] = Field(default_factory=list)

    @field_validator("label", mode="after")
    @classmethod
    def _a_label_adds_to_the_value(cls, label: str, info: ValidationInfo) -> str:
        """A label that repeats the value names nothing more."""
        return "" if label == info.data.get("value") else label

    def shown(self) -> str:
        """The value with its label."""
        return f"{self.value} ({self.label})" if self.label else self.value

    def lines(self) -> list[str]:
        return [f"{self.display_name}: {self.shown()}", *self.notes]

    def redacted(self, redact: Callable[[str], str]) -> ParameterFact:
        return self.model_copy(
            update={
                "value": redact(self.value),
                "label": redact(self.label),
                "notes": [redact(note) for note in self.notes],
            }
        )


class StepFact(CamelModel):
    """One step of the strategy, or of the draft while nothing is built.

    ``step_id`` names the step or the criterion; the facts part does not show it.
    """

    model_config = ConfigDict(frozen=True)

    step_id: str
    display_name: str
    operator: str | None = None
    count: int | None = None
    # Why the step runs its search, as its recorded reason reads.
    reason: str = ""
    parameters: list[ParameterFact] = Field(default_factory=list)
    # What the site answered when it refused the step, whole.
    error: str = ""
    # The count the step held before this turn's first edit of it.
    count_before: int | None = None

    def lines(self, noun: str) -> list[str]:
        title = (
            f"{self.operator} {self.display_name}"
            if self.operator
            else self.display_name
        )
        return [
            f"{title}: {_with_before(self.count, self.count_before, noun)}",
            *([self.reason] if self.reason else []),
            *(line for p in self.parameters for line in p.lines()),
            *([self.error] if self.error else []),
        ]

    def redacted(self, redact: Callable[[str], str]) -> StepFact:
        return self.model_copy(
            update={
                "display_name": redact(self.display_name),
                "reason": redact(self.reason),
                "parameters": [p.redacted(redact) for p in self.parameters],
                "error": redact(self.error),
            }
        )


class SourceFact(CamelModel):
    """A record or a reference a read returned, the step whose listing gave the
    record, and the check's judgement of the record against the request.

    ``values`` are the record's other words: its gene name, its chromosome and
    the orthologs of the one organism the read asked for.
    """

    model_config = ConfigDict(frozen=True)

    url: str
    record_id: str = ""
    product: str = ""
    organism: str = ""
    values: list[str] = Field(default_factory=list)
    step_id: str = ""
    step_name: str = ""
    fit: GeneFit | None = None
    why: str = ""

    def _words(self) -> list[str]:
        return [t for t in (self.product, self.organism, *self.values) if t]

    def _fit(self) -> str:
        return "" if self.fit is None else f" (the check judged its fit {self.fit})"

    def described(self) -> str:
        """The record's id and words, its fit, and its link."""
        named = ", ".join(t for t in (self.record_id, *self._words()) if t)
        return f"{named}{self._fit()}: {self.url}" if named else self.url

    def where(self) -> str:
        return f"Read from {self.step_name}" if self.step_name else "Read"

    def line(self) -> str:
        return f"{self.where()}: {self.described()}"

    def redacted(self, redact: Callable[[str], str]) -> SourceFact:
        return self.model_copy(
            update={
                "url": redact(self.url),
                "product": redact(self.product),
                "organism": redact(self.organism),
                "values": [redact(value) for value in self.values],
                "step_name": redact(self.step_name),
                "why": redact(self.why),
            }
        )


class ListedRecord(CamelModel):
    """One id a listing returned, and the site's page of its record."""

    model_config = ConfigDict(frozen=True)

    record_id: str
    url: str


class ListedFact(CamelModel):
    """The ids a listing or a sample of one step returned, under that step."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    step_name: str = ""
    records: list[ListedRecord] = Field(default_factory=list)

    def line(self) -> str:
        ids = ", ".join(r.record_id for r in self.records)
        return f"Listed from {self.step_name}: {ids}"

    def redacted(self, redact: Callable[[str], str]) -> ListedFact:
        return self.model_copy(update={"step_name": redact(self.step_name)})


class RetiredFact(CamelModel):
    """A requirement the researcher withdrew or an answer replaced."""

    model_config = ConfigDict(frozen=True)

    requirement: str
    state: RetiredState
    replaced_by: str = ""

    @computed
    def sentence(self) -> str:
        if self.state == "replaced" and self.replaced_by:
            return f"'{self.requirement}' is replaced by {self.replaced_by}"
        return f"'{self.requirement}' is withdrawn"

    def redacted(self, redact: Callable[[str], str]) -> RetiredFact:
        return self.model_copy(
            update={
                "requirement": redact(self.requirement),
                "replaced_by": redact(self.replaced_by),
            }
        )


class SavedSetFact(CamelModel):
    """A gene set or a control set this conversation saved on this turn."""

    model_config = ConfigDict(frozen=True)

    kind: SavedKind
    name: str
    count: int | None = None

    def line(self) -> str:
        what = "gene set" if self.kind == "gene_set" else "control set"
        held = "" if self.count is None else f", {_counted(self.count, 'gene')}"
        return f"Saved {what} {self.name}{held}"

    def redacted(self, redact: Callable[[str], str]) -> SavedSetFact:
        return self.model_copy(update={"name": redact(self.name)})


class TurnFacts(CamelModel):
    """Everything a turn shows beside its reply, and every fact a reference of
    the reply renders. ``comparisons`` and ``statistics`` alone make no facts
    part: their cards show them."""

    model_config = ConfigDict(frozen=True)

    record_noun: str = "gene"
    steps: list[StepFact] = Field(default_factory=list)
    # True while the steps are the draft's criteria and nothing is built.
    draft: bool = False
    root_count: int | None = None
    # The root's count before this turn's first edit.
    root_count_before: int | None = None
    # The strategy's most recent change, made by this turn or an earlier one.
    last_change: LastChange | None = None
    # The titles of the steps this turn deleted.
    removed: list[str] = Field(default_factory=list)
    strategy_url: str | None = None
    caveats: list[Caveat] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    column_fits: list[ColumnFit] = Field(default_factory=list)
    retired: list[RetiredFact] = Field(default_factory=list)
    saved: list[SavedSetFact] = Field(default_factory=list)
    control_results: list[ControlResultFact] = Field(default_factory=list)
    # What the turn's reads returned, each under the step it was read from.
    sources: list[SourceFact] = Field(default_factory=list)
    # The ids each listing of this turn returned, under the step it listed.
    listed: list[ListedFact] = Field(default_factory=list)
    # The genes the message names that the site resolved to its records.
    named_genes: list[SourceFact] = Field(default_factory=list)
    comparisons: list[ComparisonFact] = Field(default_factory=list)
    # The statistics the EDA service computed on the thread. Their card shows them.
    statistics: list[StatisticFact] = Field(default_factory=list)
    stopped_check: str = ""
    refusal: str = ""
    # The researcher's messages of the thread. A number they write is their word.
    request_messages: list[str] = Field(default_factory=list, exclude=True)

    @field_validator("caveats", mode="after")
    @classmethod
    def _one_drawer_per_measurement(
        cls, caveats: list[Caveat], info: ValidationInfo
    ) -> list[Caveat]:
        """A measurement a step row shows as a note is no caveat as well."""
        steps: list[StepFact] = info.data.get("steps", [])
        noted = {
            (step.step_id, p.display_name)
            for step in steps
            for p in step.parameters
            if p.notes
        }
        return [c for c in caveats if not _drawn_by_a_row(c, noted)]

    @field_validator("column_fits", mode="after")
    @classmethod
    def _one_row_per_column(
        cls, fits: list[ColumnFit], info: ValidationInfo
    ) -> list[ColumnFit]:
        """A column is one row: its latest read, and none when a caveat shows it."""
        caveats: list[Caveat] = info.data.get("caveats", [])
        drawn = {key for c in caveats if (key := _sampled_column(c)) is not None}
        latest = {fit.column_key: fit for fit in fits}
        return [fit for key, fit in latest.items() if key not in drawn]

    def empty(self) -> bool:
        return not any(
            (
                self.steps,
                self.removed,
                self.strategy_url,
                self.caveats,
                self.gaps,
                self.column_fits,
                self.retired,
                self.saved,
                self.control_results,
                self.sources,
                self.listed,
                self.named_genes,
                self.stopped_check,
                self.refusal,
            )
        )

    def step(self, step_id: str) -> StepFact | None:
        """The step or criterion of that id, or None."""
        return next((s for s in self.steps if s.step_id == step_id), None)

    def lines(self) -> list[str]:
        """Every line the facts part shows, in the order it shows them, a row
        for each compared variant and each statistic, which their cards draw."""
        noun = self.record_noun
        root = (
            []
            if self.root_count is None
            else [
                f"Result: {_with_before(self.root_count, self.root_count_before, noun)}"
            ]
        )
        return [
            *(line for step in self.steps for line in self._step_rows(step)),
            *root,
            *([] if self.last_change is None else [self.last_change.line(noun)]),
            *(f"Removed {title}" for title in self.removed),
            *([] if self.strategy_url is None else [self.strategy_url]),
            *(caveat.sentence for caveat in self.caveats),
            *(gap.sentence for gap in self.gaps),
            *(fit.sentence for fit in self.column_fits),
            *(retired.sentence for retired in self.retired),
            *(saved.line() for saved in self.saved),
            *(result.sentence for result in self.control_results),
            *(v.row(noun) for c in self.comparisons for v in c.variants),
            *(line for s in self.statistics for line in s.lines()),
            *(s.line() for s in self.sources if not s.step_id),
            *(f"Named in the message: {gene.described()}" for gene in self.named_genes),
            *([self.stopped_check] if self.stopped_check else []),
            *([self.refusal] if self.refusal else []),
        ]

    def _step_rows(self, step: StepFact) -> list[str]:
        return [
            *step.lines(self.record_noun),
            *(s.line() for s in self.sources if s.step_id == step.step_id),
            *(
                listed.line()
                for listed in self.listed
                if listed.step_id == step.step_id
            ),
        ]

    def text(self) -> str:
        return "\n".join(self.lines())

    def carries(self, caveat: ValueCaveat) -> bool:
        """Whether a step row shows this value with who set it and its measurement."""
        return any(
            step.step_id == caveat.criterion_id
            and p.display_name == caveat.param_display_name
            and p.source == caveat.source
            and p.notes
            for step in self.steps
            for p in step.parameters
        )

    def redacted(self, redact: Callable[[str], str]) -> TurnFacts:
        return self.model_copy(
            update={
                "steps": [step.redacted(redact) for step in self.steps],
                "last_change": self.last_change and self.last_change.redacted(redact),
                "removed": [redact(title) for title in self.removed],
                "strategy_url": None
                if self.strategy_url is None
                else redact(self.strategy_url),
                "caveats": [caveat.redacted(redact) for caveat in self.caveats],
                "gaps": [gap.redacted(redact) for gap in self.gaps],
                "column_fits": [
                    fit.model_copy(
                        update={
                            "criterion_text": redact(fit.criterion_text),
                            "display_name": redact(fit.display_name),
                            "bound_value": redact(fit.bound_value),
                        }
                    )
                    for fit in self.column_fits
                ],
                "retired": [retired.redacted(redact) for retired in self.retired],
                "saved": [saved.redacted(redact) for saved in self.saved],
                "control_results": [
                    result.redacted(redact) for result in self.control_results
                ],
                "sources": [source.redacted(redact) for source in self.sources],
                "listed": [listed.redacted(redact) for listed in self.listed],
                "named_genes": [gene.redacted(redact) for gene in self.named_genes],
                "comparisons": [c.redacted(redact) for c in self.comparisons],
                "statistics": [s.redacted(redact) for s in self.statistics],
                "stopped_check": redact(self.stopped_check),
                "refusal": redact(self.refusal),
            }
        )


def _sampled_column(caveat: Caveat) -> tuple[int, str] | None:
    match caveat:
        case SampleCaveat():
            return caveat.fit.column_key
        case _:
            return None


def _drawn_by_a_row(caveat: Caveat, noted: set[tuple[str, str]]) -> bool:
    match caveat:
        case (
            AssumedValueCaveat()
            | UnmeasuredValueCaveat()
            | ChoiceCaveat()
            | PhraseCaveat()
        ):
            return (caveat.criterion_id, caveat.param_display_name) in noted
        case _:
            return False


def uncarried_assumptions(
    caveats: Sequence[ValueCaveat], facts: TurnFacts | None
) -> int:
    """How many values the request did not state, and that narrow their step,
    no step row shows with who set them and their measurement."""
    narrowing = [c for c in caveats if c.kind == "assumed_value"]
    return sum(1 for c in narrowing if facts is None or not facts.carries(c))


__all__ = [
    "ListedFact",
    "ListedRecord",
    "ParameterFact",
    "RetiredFact",
    "SavedSetFact",
    "SourceFact",
    "StepFact",
    "TurnFacts",
    "counted",
    "uncarried_assumptions",
]
