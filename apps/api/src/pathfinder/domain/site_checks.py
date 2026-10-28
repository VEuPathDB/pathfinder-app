from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, model_validator
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.validation import StepValidation

from pathfinder.domain.count_words import counted
from pathfinder.domain.expression_fit import ExpressionFit
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.words import words_of
from pathfinder.domain.tally_facts import TallyFact

type CheckStatus = Literal["pass", "fail", "unchecked"]
type UncheckedReason = Literal["no_check", "site_unanswered", "site_refused"]
type StepCheckKind = Literal[
    "step_valid",
    "bound_values",
    "combine_counts",
    "result_count",
    "expression_fit",
    "tally",
    "step_columns",
]

_STRUCTURE_KINDS: frozenset[str] = frozenset(
    {ConstraintKind.COMBINATION.value, "combine_counts"}
)


class SiteCheck(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: ConstraintKind | StepCheckKind
    subject: str = Field(min_length=1)
    status: CheckStatus
    evidence: str = Field(min_length=1)
    requirement: str = ""
    why_unchecked: UncheckedReason | None = None

    @model_validator(mode="after")
    def _an_unchecked_check_says_why(self) -> SiteCheck:
        if (self.status == "unchecked") != (self.why_unchecked is not None):
            msg = "a check is unchecked exactly when it names why"
            raise ValueError(msg)
        return self

    @property
    def site_unanswered(self) -> bool:
        return self.why_unchecked == "site_unanswered"

    @property
    def breaks_the_structure(self) -> bool:
        return self.status == "fail" and self.kind in _STRUCTURE_KINDS

    def texts(self) -> list[str]:
        return [self.subject, self.evidence]

    def redacted(self, redact: Callable[[str], str]) -> SiteCheck:
        return self.model_copy(
            update={"subject": redact(self.subject), "evidence": redact(self.evidence)}
        )


class SiteCheckGap(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["site_check"] = "site_check"
    check: SiteCheck

    @computed
    def sentence(self) -> str:
        return f"'{self.check.subject}': {self.check.evidence}"

    def texts(self) -> list[str]:
        return [self.check.subject]

    def redacted(self, redact: Callable[[str], str]) -> SiteCheckGap:
        return self.model_copy(update={"check": self.check.redacted(redact)})

    @property
    def fails_the_check(self) -> bool:
        return True


def failed(checks: Sequence[SiteCheck]) -> list[SiteCheckGap]:
    return [SiteCheckGap(check=check) for check in checks if check.status == "fail"]


class SiteStep(CamelModel):
    model_config = ConfigDict(frozen=True)

    title: str
    wdk_step_id: int
    count: int | None = None
    record_class: str | None = None
    validation: StepValidation | None = None

    @property
    def named(self) -> str:
        return f"step {self.wdk_step_id} ('{self.title}')"


_STRATEGY = "the strategy on the site"


def unanswered_checks(why: str) -> list[SiteCheck]:
    return [
        SiteCheck(
            kind=kind,
            subject=_STRATEGY,
            status="unchecked",
            evidence=why,
            why_unchecked="site_unanswered",
        )
        for kind in ("step_valid", "bound_values", "result_count")
    ]


def unanswered_columns(step: str) -> SiteCheck:
    return SiteCheck(
        kind="step_columns",
        subject=step,
        status="unchecked",
        evidence=f"the site did not answer the column read of {step}",
        why_unchecked="site_unanswered",
    )


def validity_check(steps: Sequence[SiteStep]) -> SiteCheck:
    rejected = [s for s in steps if s.validation is not None and s.validation.rejects()]
    checked = [
        s for s in steps if s.validation is not None and s.validation.was_checked()
    ]
    if rejected:
        named = "; ".join(
            f"{s.named}: {'; '.join(s.validation.messages()) or 'invalid'}"
            for s in rejected
            if s.validation is not None
        )
        return SiteCheck(
            kind="step_valid",
            subject=_STRATEGY,
            status="fail",
            evidence=f"the site marks {counted(len(rejected), 'step')} invalid: {named}",
        )
    if not checked:
        return SiteCheck(
            kind="step_valid",
            subject=_STRATEGY,
            status="unchecked",
            evidence="the site states the validity of no step",
            why_unchecked="no_check",
        )
    return SiteCheck(
        kind="step_valid",
        subject=_STRATEGY,
        status="pass",
        evidence=f"the site marks {len(checked)} of {counted(len(steps), 'step')} valid",
    )


class HeldValue(CamelModel):
    model_config = ConfigDict(frozen=True)

    step: str
    param: str
    bound: str
    site: str | None


def _held_sentence(value: HeldValue) -> str:
    held = "no value" if value.site is None else repr(value.site)
    return (
        f"{value.step} holds {held} for {value.param}, the spec binds {value.bound!r}"
    )


def bound_values_check(compared: int, differing: Sequence[HeldValue]) -> SiteCheck:
    if differing:
        return SiteCheck(
            kind="bound_values",
            subject=_STRATEGY,
            status="fail",
            evidence="; ".join(_held_sentence(value) for value in differing),
        )
    if not compared:
        return SiteCheck(
            kind="bound_values",
            subject=_STRATEGY,
            status="unchecked",
            evidence="no step of the strategy binds a value to compare",
            why_unchecked="no_check",
        )
    return SiteCheck(
        kind="bound_values",
        subject=_STRATEGY,
        status="pass",
        evidence=(
            f"the site holds every value the spec binds on "
            f"{counted(compared, 'search step')}"
        ),
    )


class JoinedCounts(CamelModel):
    model_config = ConfigDict(frozen=True)

    title: str
    operator: CombineOp
    left: int | None
    right: int | None
    joined: int | None

    @property
    def set_operation(self) -> bool:
        return self.operator is not CombineOp.COLOCATE

    def _limits(self, left: int, right: int) -> tuple[int, int] | None:
        if self.operator is CombineOp.INTERSECT:
            return 0, min(left, right)
        if self.operator is CombineOp.UNION:
            return max(left, right), left + right
        if self.operator in _AT_MOST_LEFT:
            return 0, left
        if self.operator in _AT_MOST_RIGHT:
            return 0, right
        return None

    def holds(self) -> bool | None:
        if self.left is None or self.right is None or self.joined is None:
            return None
        limits = self._limits(self.left, self.right)
        if limits is None:
            return None
        return limits[0] <= self.joined <= limits[1]

    @property
    def sentence(self) -> str:
        return (
            f"{self.operator.value} '{self.title}' holds {self.joined:,} from "
            f"inputs of {self.left:,} and {self.right:,}"
        )


_AT_MOST_LEFT = frozenset({CombineOp.MINUS, CombineOp.LONLY})
_AT_MOST_RIGHT = frozenset({CombineOp.RMINUS, CombineOp.RONLY})


def _combine_check(
    status: CheckStatus, evidence: str, why: UncheckedReason | None = None
) -> SiteCheck:
    return SiteCheck(
        kind="combine_counts",
        subject=_STRATEGY,
        status=status,
        evidence=evidence,
        why_unchecked=why,
    )


def combine_counts_check(joins: Sequence[JoinedCounts]) -> SiteCheck | None:
    if not any(join.set_operation for join in joins):
        return None
    read = [join for join in joins if join.holds() is not None]
    if not read:
        return _combine_check(
            "unchecked",
            "the site counted no combine together with its inputs",
            "site_unanswered",
        )
    broken = [join for join in read if join.holds() is False]
    if broken:
        named = "; ".join(join.sentence for join in broken)
        return _combine_check("fail", f"a count its operator cannot hold: {named}")
    named = "; ".join(join.sentence for join in read)
    return _combine_check(
        "pass", f"each combine holds a count its operator allows: {named}"
    )


def result_count_check(root: SiteStep | None) -> SiteCheck:
    if root is None or root.count is None:
        return SiteCheck(
            kind="result_count",
            subject=_STRATEGY,
            status="unchecked",
            evidence="the site did not count the result step",
            why_unchecked="site_unanswered",
        )
    if root.count == 0:
        return SiteCheck(
            kind="result_count",
            subject=_STRATEGY,
            status="fail",
            evidence=f"the result {root.named} holds no record on the site",
        )
    return SiteCheck(
        kind="result_count",
        subject=_STRATEGY,
        status="pass",
        evidence=f"the result {root.named} holds {counted(root.count, 'record')}",
    )


def expression_fit_checks(fits: Sequence[ExpressionFit]) -> list[SiteCheck]:
    return [
        SiteCheck(
            kind="expression_fit",
            subject=f"phyletic expression {fit.expression}",
            status="fail" if fit.failing or fit.unmatched else "pass",
            evidence=fit.sentence,
        )
        for fit in fits
    ]


def tally_checks(tallies: Sequence[TallyFact], live: Sequence[int]) -> list[SiteCheck]:
    return [
        SiteCheck(
            kind="tally",
            subject=tally.title,
            status="pass",
            evidence=(
                f"the site counted {counted(tally.total, tally.record_noun)} of "
                f"step {tally.wdk_step_id} over {counted(tally.distinct, 'value')}"
            ),
        )
        for tally in tallies
        if tally.wdk_step_id in live
    ]


class OrganismCount(CamelModel):
    model_config = ConfigDict(frozen=True)

    organism: str
    count: int


class UnreadOrganisms(CamelModel):
    model_config = ConfigDict(frozen=True)

    why: UncheckedReason
    evidence: str


class CountedOrganisms(CamelModel):
    model_config = ConfigDict(frozen=True)

    step: str
    total: int
    rows: list[OrganismCount]


def _under(organism: str, selected: str) -> bool:
    named = words_of(selected)
    return bool(named) and words_of(organism)[: len(named)] == named


def _listed(rows: Sequence[OrganismCount]) -> str:
    return ", ".join(f"{row.organism} ({row.count:,})" for row in rows)


def organism_check(
    subject: str,
    requirement: str,
    selected: frozenset[str] | None,
    read: CountedOrganisms | UnreadOrganisms | None,
) -> SiteCheck:
    def judged(
        status: CheckStatus, evidence: str, why: UncheckedReason | None = None
    ) -> SiteCheck:
        return SiteCheck(
            kind=ConstraintKind.ORGANISM,
            subject=subject,
            status=status,
            evidence=evidence,
            requirement=requirement,
            why_unchecked=why,
        )

    match read:
        case UnreadOrganisms(why=why, evidence=evidence):
            return judged("unchecked", evidence, why)
        case CountedOrganisms() as found if selected is not None:
            pass
        case _:
            return judged(
                "unchecked",
                "no step of the strategy selects the organism of its result",
                "no_check",
            )
    outside = [
        row
        for row in found.rows
        if not any(_under(row.organism, chosen) for chosen in selected)
    ]
    if outside:
        held = sum(row.count for row in outside)
        return judged(
            "fail",
            f"{held:,} of the {found.total:,} records of {found.step} hold organisms "
            f"the strategy does not select: {_listed(outside)}",
        )
    if sum(row.count for row in found.rows) < found.total:
        return judged(
            "unchecked",
            f"the site named the organisms of only some of the {found.total:,} "
            f"records of {found.step}",
            "no_check",
        )
    return judged(
        "pass",
        f"all {found.total:,} records of {found.step} hold an organism the "
        f"strategy selects: {_listed(found.rows)}",
    )


__all__ = [
    "CheckStatus",
    "CountedOrganisms",
    "HeldValue",
    "JoinedCounts",
    "OrganismCount",
    "SiteCheck",
    "SiteCheckGap",
    "SiteStep",
    "StepCheckKind",
    "UncheckedReason",
    "UnreadOrganisms",
    "bound_values_check",
    "combine_counts_check",
    "expression_fit_checks",
    "failed",
    "organism_check",
    "result_count_check",
    "tally_checks",
    "unanswered_checks",
    "unanswered_columns",
    "validity_check",
]
