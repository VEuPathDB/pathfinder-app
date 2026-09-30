"""What a check measured short of the request, and what the strategy does not
answer: typed caveats and gaps, each worded by one sentence of its own."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Discriminator

from pathfinder.domain.constraint_check import CheckGap
from pathfinder.domain.evidence import (
    ColumnFit,
    ControlTestEvidence,
    NamedControlSet,
    RequirementCheck,
    VerificationReview,
)
from pathfinder.domain.strategy.constraints import (
    ConstraintSource,
    GroundedConstraint,
    message_states,
)
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.value_caveats import (
    AssumedValueCaveat,
    ChoiceCaveat,
    LabelGapCaveat,
    UnmeasuredValueCaveat,
    assumed_value_caveats,
)
from pathfinder.domain.zero_combine import ZeroCombineCaveat


def _counted(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


class ControlsCaveat(CamelModel):
    """A control test that missed a positive or returned a negative."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["controls"] = "controls"
    positives_returned: int = 0
    positives_total: int = 0
    negatives_returned: int = 0
    negatives_total: int = 0
    # None when the tested ids were not a saved set.
    control_set: NamedControlSet | None = None

    def missed_positives(self) -> bool:
        return self.positives_returned < self.positives_total

    def returned_negatives(self) -> bool:
        return self.negatives_returned > 0

    @computed
    def sentence(self) -> str:
        """The shortfall of each set, with its counts."""
        positives = f"{self.positives_returned} of {self.positives_total}"
        negatives = f"{self.negatives_returned} of {self.negatives_total}"
        clauses = [
            *(
                [f"{positives} positive controls returned"]
                if self.missed_positives()
                else []
            ),
            *(
                [f"{negatives} negative controls returned"]
                if self.returned_negatives()
                else []
            ),
        ]
        return "; ".join(clauses)

    def texts(self) -> list[str]:
        return [] if self.control_set is None else [self.control_set.name]

    def redacted(self, redact: Callable[[str], str]) -> ControlsCaveat:
        held = self.control_set
        return self.model_copy(
            update={"control_set": None if held is None else held.redacted(redact)}
        )


class SampleCaveat(CamelModel):
    """A column of a step whose values do not all fit the bound, or that the
    site does not show."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["sample"] = "sample"
    fit: ColumnFit

    @computed
    def sentence(self) -> str:
        """The records that fit out of the step, or the column the site lacks."""
        return self.fit.sentence

    def texts(self) -> list[str]:
        return self.fit.texts()

    def redacted(self, redact: Callable[[str], str]) -> SampleCaveat:
        fit = self.fit.model_copy(
            update={"criterion_text": redact(self.fit.criterion_text)}
        )
        return self.model_copy(update={"fit": fit})


# The way the researcher asked an edit to move a step's count.
type EditDirection = Literal["loosen", "tighten", "other"]


class EditDirectionCaveat(CamelModel):
    """A step an edit was asked to loosen whose count fell, or to tighten
    whose count rose."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["edit_direction"] = "edit_direction"
    step_id: str
    step_name: str
    direction: Literal["loosen", "tighten"]
    count_before: int
    count_after: int
    noun: str = "gene"

    @computed
    def sentence(self) -> str:
        """The step, the way it was asked to move, and both of its counts."""
        moved = "fell" if self.count_after < self.count_before else "rose"
        return (
            f"'{self.step_name}' was edited to {self.direction} it, and its count "
            f"{moved} from {_counted_with_commas(self.count_before, self.noun)} "
            f"to {_counted_with_commas(self.count_after, self.noun)}"
        )

    def texts(self) -> list[str]:
        return [self.step_name]

    def redacted(self, redact: Callable[[str], str]) -> EditDirectionCaveat:
        return self.model_copy(update={"step_name": redact(self.step_name)})


def _counted_with_commas(count: int, noun: str) -> str:
    return f"{count:,} {noun}" if count == 1 else f"{count:,} {noun}s"


def edit_direction_caveats(
    direction: EditDirection,
    before: Mapping[str, int],
    after: Mapping[str, tuple[str, int | None]],
    noun: str,
) -> list[EditDirectionCaveat]:
    """Each step whose count moved against the way the edit was asked to move it.

    ``after`` holds each step's name and its count now, by step id.
    """
    if direction == "other":
        return []
    return [
        EditDirectionCaveat(
            step_id=step_id,
            step_name=name,
            direction=direction,
            count_before=was,
            count_after=now,
            noun=noun,
        )
        for step_id, was in before.items()
        if step_id in after
        for name, now in [after[step_id]]
        if now is not None and (now < was if direction == "loosen" else now > was)
    ]


class PhraseCaveat(CamelModel):
    """A several-word text sent unquoted, which matches any of its words,
    where the same words as one phrase count otherwise."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["phrase"] = "phrase"
    criterion_id: str
    param_display_name: str
    value: str
    words_count: int
    phrase_count: int

    @computed
    def sentence(self) -> str:
        """The text, its count as any of its words, and its count as a phrase."""
        return (
            f"{self.param_display_name} {self.value!r} matches any of its words: "
            f"{_counted_with_commas(self.words_count, 'gene')}; as the phrase "
            f'"{self.value}": {_counted_with_commas(self.phrase_count, "gene")}'
        )

    def texts(self) -> list[str]:
        return [self.value]

    def redacted(self, redact: Callable[[str], str]) -> PhraseCaveat:
        return self.model_copy(update={"value": redact(self.value)})


def phrase_caveats(spec: OperationalSpec | None) -> list[PhraseCaveat]:
    """Each unquoted several-word text whose phrase reading counts otherwise."""
    if spec is None:
        return []
    return [
        PhraseCaveat(
            criterion_id=c.id,
            param_display_name=c.display_name_of(m.param),
            value=m.reading.strip('"'),
            words_count=c.result_count,
            phrase_count=m.count,
        )
        for c in spec.criteria
        for m in c.measurements
        if m.kind == "wildcard_phrase"
        and m.reading.startswith('"')
        and m.param in c.resolved_params
        and m.count is not None
        and c.result_count is not None
        and m.count != c.result_count
    ]


class BuildCaveat(CamelModel):
    """A build that did not put every step on the site with genes in it."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["build"] = "build"
    pushed: int
    failed: int
    skipped: int
    empty: int

    @computed
    def sentence(self) -> str:
        """The count of each outcome of the build."""
        return (
            f"The build pushed {_counted(self.pushed, 'step')}, failed "
            f"{self.failed}, skipped {self.skipped} and left {self.empty} empty"
        )

    def texts(self) -> list[str]:
        return []

    def redacted(self, redact: Callable[[str], str]) -> BuildCaveat:
        return self


Caveat = Annotated[
    ControlsCaveat
    | SampleCaveat
    | BuildCaveat
    | AssumedValueCaveat
    | UnmeasuredValueCaveat
    | ChoiceCaveat
    | LabelGapCaveat
    | EditDirectionCaveat
    | PhraseCaveat
    | ZeroCombineCaveat,
    Discriminator("kind"),
]


def caveats_for(
    spec: OperationalSpec | None, measured: Sequence[Caveat]
) -> list[Caveat]:
    """The caveats a check measured, then the values of the spec that narrow."""
    return [*measured, *assumed_value_caveats(spec), *phrase_caveats(spec)]


def controls_caveat(test: ControlTestEvidence) -> ControlsCaveat | None:
    """The caveat of one control test, or None when it returned every positive
    and no negative."""
    positive, negative = test.positive, test.negative
    caveat = ControlsCaveat(
        positives_returned=0 if positive is None else positive.returned_count,
        positives_total=0 if positive is None else positive.controls_count,
        negatives_returned=0 if negative is None else negative.returned_count,
        negatives_total=0 if negative is None else negative.controls_count,
        control_set=test.control_set,
    )
    if caveat.missed_positives() or caveat.returned_negatives():
        return caveat
    return None


def sample_caveat(fit: ColumnFit) -> SampleCaveat | None:
    """The caveat of one column fit, or None when every record fits."""
    return None if fit.fits == "all" else SampleCaveat(fit=fit)


def measured_caveats(
    *,
    build: BuildCaveat | None,
    controls: Sequence[ControlTestEvidence],
    column_fits: Sequence[ColumnFit],
) -> list[Caveat]:
    """Every caveat one check measured, in the order the ledger lists them."""
    tested = (controls_caveat(test) for test in controls)
    columns = (sample_caveat(fit) for fit in column_fits)
    return [
        *([] if build is None else [build]),
        *(caveat for caveat in tested if caveat is not None),
        *(caveat for caveat in columns if caveat is not None),
    ]


# unshown: a text query answers the row and a sampled record shows it missing.
# unjudged: a text query answers the row and no sampled record judged it.
type RequirementGapStatus = Literal["unmet", "unexpressed", "unshown", "unjudged"]


class RequirementGap(CamelModel):
    """A requirement row the check found unmet or that no search can state."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["requirement"] = "requirement"
    text: str
    status: RequirementGapStatus

    @computed
    def sentence(self) -> str:
        """The requirement, in the researcher's words, and what is missing."""
        if self.status == "unexpressed":
            return f"'{self.text}': no search on this site states it"
        if self.status == "unshown":
            return f"'{self.text}': no sampled record shows it"
        if self.status == "unjudged":
            return f"'{self.text}': no sampled record judged it"
        return f"'{self.text}': nothing in the strategy answers it"

    @property
    def fails_the_check(self) -> bool:
        """Whether the gap holds the check short of success: a step answers
        an unjudged row, so only the records are silent on it."""
        return self.status != "unjudged"

    def texts(self) -> list[str]:
        return [self.text]

    def redacted(self, redact: Callable[[str], str]) -> RequirementGap:
        return self.model_copy(update={"text": redact(self.text)})


class WordGap(CamelModel):
    """A word the request states that no search the strategy runs can state."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["word"] = "word"
    word: str

    @computed
    def sentence(self) -> str:
        """The word, and that no search states it."""
        return f"'{self.word}': no search the strategy runs states it"

    def texts(self) -> list[str]:
        return [self.word]

    def redacted(self, redact: Callable[[str], str]) -> WordGap:
        return self.model_copy(update={"word": redact(self.word)})

    @property
    def fails_the_check(self) -> bool:
        return True


class StructureGap(CamelModel):
    """A combination the researcher stated that the strategy joins another way."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["structure"] = "structure"
    expression: str
    built: str

    @computed
    def sentence(self) -> str:
        """The combination, and the operator the strategy joins it with."""
        return f"'{self.expression}': the strategy joins it with {self.built}"

    def texts(self) -> list[str]:
        return [self.expression]

    def redacted(self, redact: Callable[[str], str]) -> StructureGap:
        return self.model_copy(update={"expression": redact(self.expression)})

    @property
    def fails_the_check(self) -> bool:
        return True


Gap = Annotated[
    RequirementGap | WordGap | StructureGap | CheckGap, Discriminator("kind")
]


def _names(text: str, words: str) -> bool:
    """Whether the text carries the words, or the words carry the text."""
    return message_states(text, words) or message_states(words, text)


def _requirement_naming(
    text: str,
    requirements: Sequence[GroundedConstraint],
    *,
    met: Sequence[str] = (),
) -> GroundedConstraint | None:
    """The one requirement of the researcher the text names, by its key.

    A requirement a ``met`` row names is not the one the text misses. A text
    that names several of the rest, or none, names no one requirement, so the
    order the requirements come in decides nothing.
    """
    named = {
        held.constraint.key: held
        for held in requirements
        if held.constraint.source is ConstraintSource.USER_EXPLICIT
        and _names(text, held.constraint.requested_value)
    }
    missing = [
        held
        for held in named.values()
        if not any(_names(row, held.constraint.requested_value) for row in met)
    ]
    found = missing or list(named.values())
    return found[0] if len(found) == 1 else None


def _names_a_requirement(text: str, requirements: Sequence[GroundedConstraint]) -> bool:
    return any(_names(text, held.constraint.requested_value) for held in requirements)


def _retired(text: str, requirements: Sequence[GroundedConstraint]) -> bool:
    held = _requirement_naming(text, requirements)
    return held is not None and held.retired


def _gap_status(row: RequirementCheck) -> RequirementGapStatus:
    shown = row.shown_status
    if shown == "unexpressed" or shown == "unjudged":
        return shown
    return "unshown" if row.no_record_shows_it else "unmet"


def check_gaps(
    *,
    structure: StructureGap | None,
    words: Sequence[str],
    review: VerificationReview,
    requirements: Sequence[GroundedConstraint] = (),
    unstated: Sequence[str] = (),
    asked: Sequence[str] = (),
) -> list[Gap]:
    """Every gap of one check, once each: the structure, the words no search
    states, the requirements no search on the site states, then each
    requirement row none of those already names.

    A gap a withdrawn or replaced requirement names is no gap. A row that
    names no requirement the thread holds, or that carries every word of a
    question the thread ``asked``, is no requirement. A row that names one
    requirement carries the requirement's own words.
    """
    live_structure = structure
    if structure is not None and _retired(structure.expression, requirements):
        live_structure = None
    live_words = [w for w in dict.fromkeys(words) if not _retired(w, requirements)]
    named = {word.casefold() for word in words}
    if structure is not None:
        named.add(structure.expression.casefold())
    rows: list[Gap] = []
    for text in dict.fromkeys(unstated):
        if text.casefold() in named or _retired(text, requirements):
            continue
        named.add(text.casefold())
        rows.append(RequirementGap(text=text, status="unexpressed"))
    met = [row.text for row in review.requirements if row.shown_status == "met"]
    for row in review.to_report():
        if not _names_a_requirement(row.text, requirements) or any(
            message_states(row.text, question) for question in asked
        ):
            continue
        held = _requirement_naming(row.text, requirements, met=met)
        text = row.text if held is None else held.constraint.requested_value
        spelled = {row.text.casefold(), text.casefold()}
        if spelled & named or (held is not None and held.retired):
            continue
        named.add(text.casefold())
        rows.append(RequirementGap(text=text, status=_gap_status(row)))
    return [
        *([] if live_structure is None else [live_structure]),
        *(WordGap(word=word) for word in live_words),
        *rows,
    ]


__all__ = [
    "BuildCaveat",
    "Caveat",
    "ControlsCaveat",
    "EditDirection",
    "EditDirectionCaveat",
    "Gap",
    "PhraseCaveat",
    "RequirementGap",
    "SampleCaveat",
    "StructureGap",
    "WordGap",
    "caveats_for",
    "check_gaps",
    "controls_caveat",
    "edit_direction_caveats",
    "measured_caveats",
    "phrase_caveats",
    "sample_caveat",
]
