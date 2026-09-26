"""What a check measured short of the request, and what the strategy does not
answer: typed caveats and gaps, each worded by one sentence of its own."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Discriminator

from pathfinder.domain.evidence import (
    ControlTestEvidence,
    SampledGene,
    VerificationReview,
)
from pathfinder.domain.strategy.step_rationale import names_the_phrase
from pathfinder.domain.strategy.words import names_a_run_of


def _names_the_number(prose: str, number: str) -> bool:
    """Whether the prose holds the number whole, not inside a longer one."""
    pattern = rf"(?<![\w.]){re.escape(number)}(?![\w]|[.,]\d)"
    return re.search(pattern, prose) is not None


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


class SampleCaveat(CamelModel):
    """A sample of the result where a gene is unclear or does not fit."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["sample"] = "sample"
    unclear: int
    misfit: int
    total: int

    @computed
    def sentence(self) -> str:
        """The unclear and the misfit genes, each out of the sample."""
        clauses = [
            *(
                [f"{self.unclear} of {self.total} sampled genes unclear"]
                if self.unclear
                else []
            ),
            *(
                [f"{self.misfit} of {self.total} sampled genes do not fit"]
                if self.misfit
                else []
            ),
        ]
        return "; ".join(clauses)


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

    def stated_by(self, prose: str) -> bool:
        """Whether the prose names every count that is not zero, or the pushed
        count when nothing failed, was skipped or came back empty."""
        shortfall = [n for n in (self.failed, self.skipped, self.empty) if n]
        return all(_names_the_number(prose, str(n)) for n in shortfall or [self.pushed])


Caveat = Annotated[
    ControlsCaveat | SampleCaveat | BuildCaveat,
    Discriminator("kind"),
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
    )
    if caveat.missed_positives() or caveat.returned_negatives():
        return caveat
    return None


def sample_caveat(genes: Sequence[SampledGene]) -> SampleCaveat | None:
    """The caveat of a sample, or None when every gene fits."""
    unclear = sum(1 for gene in genes if gene.fits == "unclear")
    misfit = sum(1 for gene in genes if gene.fits == "no")
    if not unclear and not misfit:
        return None
    return SampleCaveat(unclear=unclear, misfit=misfit, total=len(genes))


def measured_caveats(
    *,
    build: BuildCaveat | None,
    controls: Sequence[ControlTestEvidence],
    genes: Sequence[SampledGene],
) -> list[Caveat]:
    """Every caveat one check measured, in the order the ledger lists them."""
    tested = (controls_caveat(test) for test in controls)
    sampled = sample_caveat(genes)
    return [
        *([] if build is None else [build]),
        *(caveat for caveat in tested if caveat is not None),
        *([] if sampled is None else [sampled]),
    ]


class RequirementGap(CamelModel):
    """A requirement row the check found unmet or that no search can state."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["requirement"] = "requirement"
    text: str
    status: Literal["unmet", "unexpressed"]

    @computed
    def sentence(self) -> str:
        """The requirement, in the researcher's words, and what is missing."""
        if self.status == "unexpressed":
            return f"'{self.text}': no search on this site states it"
        return f"'{self.text}': nothing in the strategy answers it"

    def named_by(self, prose: str) -> bool:
        return names_a_run_of(prose, self.text)

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

    def named_by(self, prose: str) -> bool:
        return names_the_phrase(prose, self.word)

    def texts(self) -> list[str]:
        return [self.word]

    def redacted(self, redact: Callable[[str], str]) -> WordGap:
        return self.model_copy(update={"word": redact(self.word)})


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

    def named_by(self, prose: str) -> bool:
        return names_the_phrase(prose, self.expression)

    def texts(self) -> list[str]:
        return [self.expression]

    def redacted(self, redact: Callable[[str], str]) -> StructureGap:
        return self.model_copy(update={"expression": redact(self.expression)})


Gap = Annotated[RequirementGap | WordGap | StructureGap, Discriminator("kind")]


def check_gaps(
    *,
    structure: StructureGap | None,
    words: Sequence[str],
    review: VerificationReview,
) -> list[Gap]:
    """Every gap of one check, once each: the structure, the words no search
    states, then each requirement row neither of those already names."""
    named = {word.casefold() for word in words}
    if structure is not None:
        named.add(structure.expression.casefold())
    rows: list[Gap] = [
        RequirementGap(
            text=row.text,
            status="unexpressed" if row.status == "unexpressed" else "unmet",
        )
        for row in review.to_report()
        if row.text.casefold() not in named
    ]
    return [
        *([] if structure is None else [structure]),
        *(WordGap(word=word) for word in dict.fromkeys(words)),
        *rows,
    ]


__all__ = [
    "BuildCaveat",
    "Caveat",
    "ControlsCaveat",
    "Gap",
    "RequirementGap",
    "SampleCaveat",
    "StructureGap",
    "WordGap",
    "check_gaps",
    "controls_caveat",
    "measured_caveats",
    "sample_caveat",
]
