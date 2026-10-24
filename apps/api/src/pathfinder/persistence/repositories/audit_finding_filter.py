from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select

from pathfinder.domain.audit.findings import Certainty, ErrorType, FindingStatus
from pathfinder.domain.audit.scope import CheckName
from pathfinder.persistence.models import AuditFinding

__all__ = ["FindingFilter", "filtered"]

type _Query = Select[tuple[AuditFinding]]


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
        query = query.where(AuditFinding.error_type.in_(where.error_types))
    if where.certainties:
        query = query.where(AuditFinding.certainty.in_(where.certainties))
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
