from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from sqlalchemy import ColumnElement, Select, exists, func, select
from sqlalchemy.orm import aliased

from pathfinder.domain.audit.findings import Certainty, ErrorType, FindingStatus
from pathfinder.domain.audit.scope import CheckName
from pathfinder.persistence.models import AuditFinding, AuditVerdict

__all__ = [
    "FindingFilter",
    "effective_certainty",
    "effective_error_type",
    "filtered",
    "rejected_by_review",
]

type _Query = Select[tuple[AuditFinding]]


def _reviewed(key: str) -> ColumnElement[str | None]:
    verdict = aliased(AuditVerdict)
    return (
        select(verdict.verdict[key].astext)
        .where(verdict.finding_id == AuditFinding.id)
        .correlate(AuditFinding)
        .scalar_subquery()
    )


def effective_error_type() -> ColumnElement[str | None]:
    return func.coalesce(_reviewed("errorType"), AuditFinding.error_type)


def effective_certainty() -> ColumnElement[str | None]:
    return func.coalesce(_reviewed("certainty"), AuditFinding.certainty)


def rejected_by_review() -> ColumnElement[bool]:
    verdict = aliased(AuditVerdict)
    return exists(
        select(verdict.id)
        .where(
            verdict.finding_id == AuditFinding.id,
            verdict.verdict["verdict"].astext == "no_error",
        )
        .correlate(AuditFinding)
    )


class FindingFilter(BaseModel):
    model_config = ConfigDict(frozen=True)

    checks: tuple[CheckName, ...] = ()
    statuses: tuple[FindingStatus, ...] = ()
    error_types: tuple[ErrorType, ...] = ()
    certainties: tuple[Certainty, ...] = ()
    genome: str | None = None
    screened_genome: str | None = None
    sampled: bool | None = None
    named: bool | None = None
    keys: tuple[str, ...] | None = None
    excluded_keys: tuple[str, ...] = ()
    ids: tuple[int, ...] | None = None


def _by_kind(query: _Query, where: FindingFilter) -> _Query:
    if where.checks:
        query = query.where(AuditFinding.check_name.in_(where.checks))
    if where.statuses:
        query = query.where(AuditFinding.status.in_(where.statuses))
    if where.error_types:
        query = query.where(
            effective_error_type().in_(where.error_types), ~rejected_by_review()
        )
    if where.certainties:
        query = query.where(
            effective_certainty().in_(where.certainties), ~rejected_by_review()
        )
    if where.named is not None:
        named = AuditFinding.error_type.is_not(None)
        query = query.where(named if where.named else ~named)
    return query


def _by_place(query: _Query, where: FindingFilter) -> _Query:
    if where.genome is not None:
        query = query.where(AuditFinding.genome == where.genome)
    if where.screened_genome is not None:
        query = query.where(AuditFinding.screened_genome == where.screened_genome)
    if where.sampled is not None:
        query = query.where(AuditFinding.sampled.is_(where.sampled))
    if where.keys is not None:
        query = query.where(AuditFinding.target_key.in_(where.keys))
    if where.excluded_keys:
        query = query.where(AuditFinding.target_key.not_in(where.excluded_keys))
    if where.ids is not None:
        query = query.where(AuditFinding.id.in_(where.ids))
    return query


def filtered(query: _Query, where: FindingFilter) -> _Query:
    return _by_place(_by_kind(query, where), where)
