from __future__ import annotations

from collections.abc import Mapping, Sequence

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

from pathfinder.domain.audit.findings import ErrorType
from pathfinder.domain.audit.verdicts import VerdictKind
from pathfinder.evals.case import ExpectedOutcome
from pathfinder.evals.difference import CaseDifference
from pathfinder.services.audit.verdicts import VerdictView

NO_VERDICT = "(none)"


class ObservedVerdict(CamelModel):
    model_config = ConfigDict(frozen=True)

    verdict: VerdictKind
    error_type: ErrorType | None
    cause: str


def newest_verdicts(views: Sequence[VerdictView]) -> dict[str, ObservedVerdict]:
    newest: dict[str, ObservedVerdict] = {}
    for view in sorted(views, key=lambda view: view.created_at):
        judged = view.verdict
        for gene in judged.genes:
            newest[gene] = ObservedVerdict(
                verdict=judged.verdict,
                error_type=judged.error_type,
                cause=judged.cause,
            )
    return newest


def verdict_differences(
    expected: ExpectedOutcome, observed: Mapping[str, ObservedVerdict]
) -> list[CaseDifference]:
    differences: list[CaseDifference] = []
    for gene, kind in expected.verdicts.items():
        found = observed.get(gene)
        actual = NO_VERDICT if found is None else found.verdict
        if actual != kind:
            differences.append(
                CaseDifference(field=f"verdicts.{gene}", expected=kind, actual=actual)
            )
        cause = "" if found is None else found.cause
        differences.extend(
            CaseDifference(field=f"verdictCauses.{gene}", expected=phrase, actual=cause)
            for phrase in expected.verdict_causes.get(gene, [])
            if phrase.casefold() not in cause.casefold()
        )
    return differences


__all__ = ["ObservedVerdict", "newest_verdicts", "verdict_differences"]
