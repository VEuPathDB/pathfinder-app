"""Every audit read as a statistic fact, one row per number or name it holds, under a dotted path a reply's reference names."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from uuid import UUID

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter
from veupathdb_mcp.audit import RateBounds

from pathfinder.ai.graph.turn_records import ReadRecord
from pathfinder.domain.audit.findings import AuditOutcome
from pathfinder.domain.audit.planning import PlanRequest, ScopeProposal
from pathfinder.domain.statistic_facts import (
    StatisticFact,
    StatisticRowFact,
    statistic_id,
)
from pathfinder.services.audit.finding_views import FindingDetail, FindingPage
from pathfinder.services.audit.views import AuditRunSummary, AuditRunView
from pathfinder.services.gene_records.read import gene_record_url

_JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


def _path(prefix: str, key: str) -> str:
    return f"{prefix}.{key}" if prefix else key


def _rows(path: str, value: JsonValue) -> Iterator[StatisticRowFact]:
    match value:
        case dict():
            for key, item in value.items():
                yield from _rows(_path(path, key), item)
        case list():
            for index, item in enumerate(value):
                yield from _rows(_path(path, str(index)), item)
        case str():
            yield StatisticRowFact(name=path, value=value)
        case None:
            return
        case _:
            yield StatisticRowFact(name=path, value=json.dumps(value))


def json_rows(prefix: str, value: object) -> list[StatisticRowFact]:
    return list(_rows(prefix, _JSON.validate_python(value)))


def _dumped(model: BaseModel | None, *, exclude: set[str] | None = None) -> object:
    if model is None:
        return None
    return model.model_dump(mode="json", by_alias=True, exclude=exclude)


def check_fact(
    tool_name: str, subjects: Sequence[str], answer: BaseModel
) -> StatisticFact:
    return StatisticFact(
        id=statistic_id("gene_check", [tool_name, *subjects]),
        kind="gene_check",
        title=f"{tool_name} of {', '.join(subjects)}",
        rows=json_rows("", _dumped(answer)),
    )


class AuditRead[T](CamelModel):
    model_config = ConfigDict(frozen=True)

    answer: T
    fact_id: str


def gene_records(site_id: str, genes: Iterable[str]) -> list[ReadRecord]:
    return [
        ReadRecord(record_id=gene, url=gene_record_url(site_id, gene))
        for gene in dict.fromkeys(genes)
    ]


def audit_finding_fact(run_id: UUID, detail: FindingDetail) -> StatisticFact:
    finding = detail.finding
    return StatisticFact(
        id=statistic_id("audit_finding", [str(run_id), str(finding.id)]),
        kind="audit_finding",
        title=f"Finding {finding.id} of audit run {run_id}",
        rows=json_rows("", _dumped(detail)),
    )


def audit_run_fact(view: AuditRunView) -> StatisticFact:
    return StatisticFact(
        id=statistic_id("audit_run", [str(view.run.id)]),
        kind="audit_run",
        title=f"Audit run {view.run.id}",
        rows=json_rows("", _dumped(view)),
    )


def audit_runs_fact(runs: Sequence[AuditRunSummary]) -> StatisticFact:
    return StatisticFact(
        id=statistic_id("audit_runs", [str(run.id) for run in runs]),
        kind="audit_runs",
        title="The audit runs of this researcher",
        rows=json_rows("runs", [_dumped(run) for run in runs]),
    )


def findings_fact(run_id: UUID, page: FindingPage) -> StatisticFact:
    return StatisticFact(
        id=statistic_id(
            "audit_findings",
            [str(run_id), str(page.offset), *(str(f.id) for f in page.findings)],
        ),
        kind="audit_findings",
        title=f"Findings of audit run {run_id}",
        rows=json_rows("", _dumped(page)),
    )


def _asked(request: PlanRequest) -> list[str]:
    return [
        request.site_id,
        *request.genomes,
        *(request.checks or ()),
        *(target.key for target in request.targets),
        str(request.confirm_limit),
    ]


def plan_fact(proposal: ScopeProposal) -> StatisticFact:
    return StatisticFact(
        id=statistic_id("audit_plan", _asked(proposal.request)),
        kind="audit_plan",
        title=f"Audit plan on {proposal.request.site_id}",
        rows=json_rows("", _dumped(proposal)),
    )


def start_fact(outcome: AuditOutcome) -> StatisticFact:
    return StatisticFact(
        id=statistic_id("audit_start", [str(outcome.run_id)]),
        kind="audit_start",
        title=f"Audit run {outcome.run_id} started",
        rows=json_rows("", _dumped(outcome)),
    )


def rate_fact(bounds: RateBounds) -> StatisticFact:
    counts = (bounds.confirmed, bounds.checked, bounds.unresolved)
    return StatisticFact(
        id=statistic_id("audit_rate", [str(count) for count in counts]),
        kind="audit_rate",
        title=(
            f"Rate of {bounds.confirmed} confirmed of {bounds.checked} checked, "
            f"{bounds.unresolved} unresolved"
        ),
        rows=json_rows("", _dumped(bounds)),
    )
