"""What a check measured short of the request, and what the strategy does not
answer: typed caveats and gaps, each worded by one sentence of its own."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Discriminator

from pathfinder.domain.column_fit import ColumnFit
from pathfinder.domain.count_words import counted
from pathfinder.domain.evidence import ControlTestEvidence, NamedControlSet
from pathfinder.domain.organism_caveat import RecordsOrganismCaveat
from pathfinder.domain.reading_caveats import ReadingCaveat, reading_caveats
from pathfinder.domain.requirement_naming import names_a_retired_requirement
from pathfinder.domain.site_checks import SiteCheckGap
from pathfinder.domain.strategy.constraints import GroundedConstraint
from pathfinder.domain.strategy.operational_spec import OperationalSpec
from pathfinder.domain.strategy.value_binding import plain_value
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
            f"{moved} from {counted(self.count_before, self.noun)} "
            f"to {counted(self.count_after, self.noun)}"
        )

    def texts(self) -> list[str]:
        return [self.step_name]

    def redacted(self, redact: Callable[[str], str]) -> EditDirectionCaveat:
        return self.model_copy(update={"step_name": redact(self.step_name)})


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
    """A several-word text sent unquoted, which the site matches by any of its
    words, where the same words as one phrase count otherwise."""

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
            f"{self.param_display_name} {self.value!r} is unquoted, so the site "
            f"matches any of its words: "
            f"{counted(self.words_count, 'gene')}; as the phrase: "
            f"{counted(self.phrase_count, 'gene')}"
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
            value=plain_value(c.resolved_params[m.param].value),
            words_count=c.result_count,
            phrase_count=m.count,
        )
        for c in spec.criteria
        for m in c.measurements
        if m.kind == "phrase_reading"
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
    | ReadingCaveat
    | ZeroCombineCaveat
    | RecordsOrganismCaveat,
    Discriminator("kind"),
]


def caveats_for(
    spec: OperationalSpec | None, measured: Sequence[Caveat]
) -> list[Caveat]:
    """The caveats a check measured, then the values of the spec that narrow."""
    return [
        *measured,
        *assumed_value_caveats(spec),
        *phrase_caveats(spec),
        *reading_caveats(spec),
    ]


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


class RequirementGap(CamelModel):
    """A requirement the framing pass found no search on the site states."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["requirement"] = "requirement"
    text: str

    @computed
    def sentence(self) -> str:
        """The requirement, in the researcher's words, and what is missing."""
        return f"'{self.text}': no search on this site states it"

    @property
    def fails_the_check(self) -> bool:
        return True

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


Gap = Annotated[
    RequirementGap | WordGap | SiteCheckGap,
    Discriminator("kind"),
]


def check_gaps(
    *,
    words: Sequence[str],
    requirements: Sequence[GroundedConstraint] = (),
    unstated: Sequence[str] = (),
) -> list[Gap]:
    """The words no search states, then the requirements no search on the site
    states, once each. A gap a withdrawn or replaced requirement names is no gap."""
    named = {word.casefold() for word in words}
    rows: list[Gap] = [
        WordGap(word=w)
        for w in dict.fromkeys(words)
        if not names_a_retired_requirement(w, requirements)
    ]
    for text in dict.fromkeys(unstated):
        if text.casefold() in named or names_a_retired_requirement(text, requirements):
            continue
        named.add(text.casefold())
        rows.append(RequirementGap(text=text))
    return rows


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
    "WordGap",
    "caveats_for",
    "check_gaps",
    "controls_caveat",
    "edit_direction_caveats",
    "measured_caveats",
    "phrase_caveats",
    "sample_caveat",
]
