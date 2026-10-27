from __future__ import annotations

from collections.abc import Collection, Mapping

from pathfinder.domain.site_checks import CheckStatus, SiteCheck
from pathfinder.domain.strategy.constraints import (
    GENE_ANSWERING_CLASSES,
    GENE_RECORD_NOUNS,
    Constraint,
    ConstraintStatus,
    GroundedConstraint,
    is_blocking,
    record_noun,
)
from pathfinder.domain.strategy.requirement_reports import RecordRole
from pathfinder.domain.strategy.words import whole_run_of

_UNMET = frozenset({ConstraintStatus.SUBSTITUTED, ConstraintStatus.UNGROUNDABLE})


def _judged(c: Constraint, status: CheckStatus, evidence: str) -> SiteCheck:
    return SiteCheck(
        kind=c.kind,
        subject=c.requested_value,
        status=status,
        evidence=evidence,
        requirement=c.key,
        why_unchecked="no_check" if status == "unchecked" else None,
    )


def grounded_check(grounded: GroundedConstraint) -> SiteCheck:
    c = grounded.constraint
    if grounded.status in _UNMET:
        said = grounded.note or f"the strategy states {grounded.realized_value}"
        return _judged(c, "fail" if is_blocking(grounded) else "unchecked", said)
    if grounded.status is ConstraintStatus.GROUNDED and grounded.realized_value:
        param = f"{grounded.realized_param} = " if grounded.realized_param else ""
        return _judged(
            c, "pass", f"the strategy states {param}{grounded.realized_value}"
        )
    return _judged(
        c, "unchecked", grounded.note or "no check reads this requirement on the site"
    )


def _class_words(record_class: str, names: Collection[str]) -> set[str]:
    return {word for name in [record_class, *names] if (word := record_noun(name))}


def classes_named(text: str, class_names: Mapping[str, Collection[str]]) -> set[str]:
    noun = record_noun(text)
    named = {
        record_class
        for record_class, names in class_names.items()
        if any(whole_run_of(noun, word) for word in _class_words(record_class, names))
    }
    if GENE_RECORD_NOUNS.intersection(noun.split()):
        named |= GENE_ANSWERING_CLASSES
    return named


def record_type_check(
    c: Constraint,
    role: RecordRole,
    named: Collection[str],
    root_class: str | None,
    step_classes: Collection[str],
) -> SiteCheck:
    if not named:
        return _judged(c, "unchecked", "the site names no record class by these words")
    if role == "through":
        through = sorted(set(step_classes) & set(named))
        if through:
            return _judged(c, "pass", f"a step of the strategy returns {through[0]}")
        return _judged(c, "fail", "no step of the strategy returns these records")
    if root_class is None:
        return _judged(c, "unchecked", "the site names no record class for the result")
    status: CheckStatus = "pass" if root_class in named else "fail"
    return _judged(c, status, f"the result step returns {root_class} records")


__all__ = ["classes_named", "grounded_check", "record_type_check"]
