"""The control counts, control gene ids and sampled-gene counts a reply states,
held to the tests the turn ran and the sample the check judged."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    EvidenceCard,
    SampledGene,
)

ControlKind = Literal["positive", "negative"]

_EMPHASIS = re.compile(r"\*+")
# A count names controls: "positive controls", or the kind as a noun ("negatives").
_COUNT = re.compile(
    r"(?<![\w.])(\d[\d,]*)\s*(?:of|out of|/)\s*(?:the\s+|all\s+)?(\d[\d,]*)\s+"
    r"(?:known\s+|reference\s+|tested\s+)?(positive|negative)"
    r"(?:\s+controls?\b|s\b)",
    re.IGNORECASE,
)
# A clause ends at a sentence end, a line break or a contrast.
_CLAUSE_END = re.compile(
    r"[.;!?]+(?=\s|$)|\n+|,?\s+(?:but|while|whereas)\s+", re.IGNORECASE
)
# A gene id starts with a letter and holds a digit: PF3D7_0102600, LmjF.01.0010,
# AGAP004707, BBOV_I000010.
_GENE_ID = re.compile(r"`((?=[^`]*\d)[A-Za-z][A-Za-z0-9]*(?:[_.-][A-Za-z0-9]+)*)`")
_STEP_ID = re.compile(r"^step\b|^step[_-]", re.IGNORECASE)
_CONTROL = re.compile(r"\bcontrols?\b", re.IGNORECASE)
_NO_CONTROL = re.compile(r"\bno\s+controls?\b", re.IGNORECASE)
_NOT_RETURNED = re.compile(
    r"\b(?:missed|missing|excluded|absent|left out|dropped)\b"
    r"|(?:\bnot|n't|\bnever)\s+(?:been\s+|be\s+)?"
    r"(?:returned|recovered|found|retrieved|captured)\b",
    re.IGNORECASE,
)
_RETURNED = re.compile(
    r"\b(?:returned|recovered|found|retrieved|captured|admitted)\b", re.IGNORECASE
)
# "all 8 sampled genes fit", "6 of 8 sampled genes fit", "2 of the 8 sampled
# genes do not fit".
_SAMPLE = re.compile(
    r"\b(?:(?P<all>all)(?:\s+(?P<all_of>\d+))?"
    r"|(?P<stated>\d+)\s*(?:of|out of|/)\s*(?:the\s+)?(?P<of>\d+))"
    r"\s+sampled\s+genes?\s+"
    r"(?P<negated>(?:do|does|did)\s+not\s+|(?:don|doesn|didn)'t\s+)?fit\b",
    re.IGNORECASE,
)


def _sets(
    tests: Iterable[ControlTestEvidence], kind: ControlKind
) -> list[ControlSetEvidence]:
    found = (test.positive if kind == "positive" else test.negative for test in tests)
    return [each for each in found if each is not None]


@dataclass(frozen=True)
class CountClaim:
    """A stated number of controls of one kind, out of a stated total.

    ``returned`` is what the clause's verb files the count under: the controls
    returned, the controls not returned, or None when the clause has no verb.
    """

    stated: int
    of: int
    kind: ControlKind
    returned: bool | None

    def text(self) -> str:
        verb = {True: " returned", False: " not returned", None: ""}[self.returned]
        return f"{self.stated} of {self.of} {self.kind} controls{verb}"

    def _held_by(self, each: ControlSetEvidence) -> bool:
        if each.controls_count != self.of:
            return False
        returned, not_returned = each.returned_count, len(each.not_returned)
        match self.returned:
            case True:
                return self.stated == returned
            case False:
                return self.stated == not_returned
            case None:
                return self.stated in (returned, not_returned)

    def unbacked(self, tests: Sequence[ControlTestEvidence]) -> str | None:
        """Why no set of this kind holds the count, or None when one does."""
        sets = _sets(tests, self.kind)
        if not sets:
            return (
                f"The reply says {self.text()}, and no control result of this "
                f"turn or of its last check holds {self.kind} controls."
            )
        if any(self._held_by(each) for each in sets):
            return None
        recorded = "; ".join(
            dict.fromkeys(
                f"{each.returned_count} of {each.controls_count} {self.kind} "
                "controls returned"
                for each in sets
            )
        )
        return f"The reply says {self.text()}; the control results recorded {recorded}."


@dataclass(frozen=True)
class IdClaim:
    """A control gene id the prose files as returned or as not returned."""

    gene_id: str
    returned: bool

    def unbacked(self, tests: Sequence[ControlTestEvidence]) -> str | None:
        """Why no set files the id where the prose does, or None when one does."""
        sets = [*_sets(tests, "positive"), *_sets(tests, "negative")]
        filed = [
            self.gene_id in each.returned
            for each in sets
            if self.gene_id in each.returned or self.gene_id in each.not_returned
        ]
        verb = "returned" if self.returned else "not returned"
        said = f"The reply says control `{self.gene_id}` was {verb}"
        if not filed:
            return (
                f"{said}; no control result of this turn or of its last check lists it."
            )
        if self.returned in filed:
            return None
        recorded = "returned" if filed[0] else "not returned"
        return f"{said}; the control test recorded it as {recorded}."


ControlClaim = CountClaim | IdClaim


def _number(text: str) -> int:
    return int(text.replace(",", ""))


def _count_claims(prose: str) -> list[ControlClaim]:
    return [
        CountClaim(
            stated=_number(match[1]),
            of=_number(match[2]),
            kind="positive" if match[3].casefold() == "positive" else "negative",
            returned=_filed_as_returned(clause),
        )
        for clause in _CLAUSE_END.split(prose)
        for match in _COUNT.finditer(clause)
    ]


def _filed_as_returned(clause: str) -> bool | None:
    """Whether the clause files its ids as returned, or None when it does not say."""
    denied = _NOT_RETURNED.search(clause) is not None
    affirmed = _RETURNED.search(_NOT_RETURNED.sub(" ", clause)) is not None
    if denied == affirmed:
        return None
    return affirmed


def _id_claims(prose: str) -> list[ControlClaim]:
    claims: list[ControlClaim] = []
    for clause in _CLAUSE_END.split(prose):
        if _CONTROL.search(clause) is None or _NO_CONTROL.search(clause):
            continue
        returned = _filed_as_returned(clause)
        if returned is None:
            continue
        claims.extend(
            IdClaim(gene_id=gene_id, returned=returned)
            for gene_id in _GENE_ID.findall(clause)
            if _STEP_ID.search(gene_id) is None
        )
    return claims


def control_claims(prose: str) -> list[ControlClaim]:
    """Every control count and control gene id the prose states."""
    plain = _EMPHASIS.sub("", prose)
    return [*_count_claims(plain), *_id_claims(plain)]


@dataclass(frozen=True)
class SampleClaim:
    """A stated number of sampled genes that fit, or do not, out of a total.

    ``stated`` None is "all"; ``of`` None is a total the prose does not give.
    """

    stated: int | None
    of: int | None
    fits: bool

    def text(self) -> str:
        count = "all" if self.stated is None else str(self.stated)
        total = "" if self.of is None else f" {self.of}"
        if self.stated is not None and self.of is not None:
            total = f" of {self.of}"
        verb = "fit" if self.fits else "do not fit"
        return f"{count}{total} sampled genes {verb}"

    def unbacked(self, genes: Sequence[SampledGene]) -> str | None:
        """Why the sample does not hold the count, or None when it does."""
        said = f"The reply says {self.text()}"
        if not genes:
            return f"{said}, and no check sampled a gene."
        fitting = sum(1 for gene in genes if gene.fits == "yes")
        misfits = [gene.gene_id for gene in genes if gene.fits == "no"]
        wanted = fitting if self.fits else len(misfits)
        stated = len(genes) if self.stated is None else self.stated
        total = len(genes) if self.of is None else self.of
        if (stated, total) == (wanted, len(genes)):
            return None
        listed = ", ".join(f"`{gene_id}`" for gene_id in misfits)
        named = f" ({listed})" if listed else ""
        unclear = len(genes) - fitting - len(misfits)
        return (
            f"{said}; the check sampled {len(genes)} genes: {fitting} fit, "
            f"{len(misfits)} do not fit{named}, {unclear} unclear."
        )


def sample_claims(prose: str) -> list[SampleClaim]:
    """Every count of sampled genes that fit, or do not, the prose states."""
    return [
        SampleClaim(
            stated=None if match["all"] else int(match["stated"]),
            of=(
                int(total)
                if (total := match["all_of"] or match["of"]) is not None
                else None
            ),
            fits=match["negated"] is None,
        )
        for match in _SAMPLE.finditer(_EMPHASIS.sub("", prose))
    ]


def unbacked_sample_claims(
    claims: Sequence[SampleClaim], genes: Sequence[SampledGene]
) -> list[str]:
    """One sentence per sampled-gene count the sample does not hold, each once."""
    found: list[str] = []
    for claim in claims:
        sentence = claim.unbacked(genes)
        if sentence is not None and sentence not in found:
            found.append(sentence)
    return found


def backing_results(
    this_turn: Iterable[ControlTestEvidence],
    last_card: EvidenceCard | None,
    offered: Iterable[ControlTestEvidence],
) -> tuple[ControlTestEvidence, ...]:
    """The control results a claim may cite: this turn's, the last check's, and
    the site's reads a separation offer holds."""
    return (*this_turn, *([] if last_card is None else last_card.controls), *offered)


def unbacked_claims(
    claims: Sequence[ControlClaim], tests: Sequence[ControlTestEvidence]
) -> list[str]:
    """One sentence per claim the turn's control tests do not hold, each once."""
    found: list[str] = []
    for claim in claims:
        sentence = claim.unbacked(tests)
        if sentence is not None and sentence not in found:
            found.append(sentence)
    return found


__all__ = [
    "ControlClaim",
    "CountClaim",
    "IdClaim",
    "SampleClaim",
    "backing_results",
    "control_claims",
    "sample_claims",
    "unbacked_claims",
    "unbacked_sample_claims",
]
