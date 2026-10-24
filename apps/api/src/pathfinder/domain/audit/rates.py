"""Each genome's error rate per check over its sample, the counts its gene targets give, and the
impact a named finding is ordered by with the inputs it was weighed from."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field
from veupathdb_mcp.audit import GeneEvidence, RateBounds, rate_with_bounds

from pathfinder.domain.audit.findings import (
    Certainty,
    ErrorType,
    FindingStatus,
    FindingTally,
    ModelRole,
)
from pathfinder.domain.audit.scope import CheckName

CERTAINTY_WEIGHT: dict[Certainty, float] = {"high": 1.0, "medium": 0.6, "low": 0.3}
CITED_IMPORTANCE = 1.0
UNCITED_IMPORTANCE = 0.5
REFERENCE_USE = 1.0
STRAIN_USE = 0.5
IMPACT_PLACES = 3

ImportanceSource = Literal["cited", "uncited", "not_read"]
UseSource = Literal["reference_strain", "other_strain", "unknown", "model_role"]


class Unresolved(CamelModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    screened: int = Field(default=0, ge=0)
    unsampled: int = Field(default=0, ge=0)
    trying: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    declined: int = Field(default=0, ge=0)
    unreached: int = Field(default=0, ge=0)
    unread: int = Field(default=0, ge=0)

    @computed
    def total(self) -> int:
        return (
            self.screened
            + self.unsampled
            + self.trying
            + self.failed
            + self.declined
            + self.unreached
            + self.unread
        )


class GenomeRate(CamelModel):
    model_config = ConfigDict(frozen=True)

    genome: str
    check: CheckName
    bounds: RateBounds | None
    unjudged: int = Field(ge=0)
    unresolved_by_status: Unresolved

    @computed
    def unresolved(self) -> int:
        return self.unresolved_by_status.total


def _side(row: FindingTally) -> str:
    match (row.status, row.judged, row.holds_error):
        case ("confirmed", False, _):
            return "unjudged"
        case ("confirmed", True, True):
            return "named"
        case ("confirmed", True, False):
            return "clean"
        case _:
            return "unresolved"


def _rate(genome: str, check: CheckName, n: Counter[str]) -> GenomeRate:
    unresolved = Unresolved.model_validate(n)
    checked = n["named"] + n["clean"]
    return GenomeRate(
        genome=genome,
        check=check,
        bounds=rate_with_bounds(n["named"], checked, unresolved.total)
        if checked
        else None,
        unjudged=n["unjudged"],
        unresolved_by_status=unresolved,
    )


def genome_rates(tally: Sequence[FindingTally]) -> list[GenomeRate]:
    counted: defaultdict[tuple[str, CheckName], Counter[str]] = defaultdict(Counter)
    for row in tally:
        side = _side(row)
        counted[row.genome, row.check][
            row.status if side == "unresolved" else side
        ] += row.count
    return [_rate(genome, check, n) for (genome, check), n in sorted(counted.items())]


class TargetFinding(CamelModel):
    model_config = ConfigDict(frozen=True)

    check: CheckName
    status: FindingStatus
    error_type: ErrorType | None
    judged: bool
    model_genome: str
    judged_genomes: tuple[str, ...]


class TargetTally(CamelModel):
    model_config = ConfigDict(frozen=True)

    genome: str
    check: CheckName
    checked: int = Field(ge=0)
    errors: int = Field(ge=0)
    unjudged: int = Field(ge=0)
    unresolved_by_status: Unresolved

    @computed
    def unresolved(self) -> int:
        return self.unresolved_by_status.total


class TargetReport(CamelModel):
    model_config = ConfigDict(frozen=True)

    genomes: list[TargetTally]
    unplaced: int = Field(ge=0)


def _target_side(target: TargetFinding, genome: str) -> str:
    match _side(
        FindingTally(
            genome=genome,
            model_genome=target.model_genome,
            check=target.check,
            status=target.status,
            error_type=target.error_type,
            judged=target.judged,
            count=1,
        )
    ):
        case "named":
            return "errors"
        case "clean":
            return "checked"
        case "unresolved":
            return target.status
        case side:
            return side


def target_report(targets: Iterable[TargetFinding]) -> TargetReport:
    counted: defaultdict[tuple[str, CheckName], Counter[str]] = defaultdict(Counter)
    unplaced = 0
    for target in targets:
        genomes = [genome for genome in target.judged_genomes if genome]
        unplaced += not genomes
        for genome in genomes:
            side = _target_side(target, genome)
            counted[genome, target.check][side] += 1
            counted[genome, target.check]["checked"] += side == "errors"
    return TargetReport(
        genomes=[
            TargetTally(
                genome=genome,
                check=check,
                checked=n["checked"],
                errors=n["errors"],
                unjudged=n["unjudged"],
                unresolved_by_status=Unresolved.model_validate(n),
            )
            for (genome, check), n in sorted(counted.items())
        ],
        unplaced=unplaced,
    )


class Importance(CamelModel):
    model_config = ConfigDict(frozen=True)

    genes: tuple[str, ...]
    source: ImportanceSource

    @computed
    def value(self) -> float:
        return CITED_IMPORTANCE if self.source == "cited" else UNCITED_IMPORTANCE


class GenomeUse(CamelModel):
    model_config = ConfigDict(frozen=True)

    genome: str
    source: UseSource
    reference: bool

    @computed
    def value(self) -> float:
        return REFERENCE_USE if self.reference else STRAIN_USE


class Weighing(CamelModel):
    model_config = ConfigDict(frozen=True)

    certainty: Certainty
    importance: Importance
    use: GenomeUse

    @computed
    def certainty_weight(self) -> float:
        return CERTAINTY_WEIGHT[self.certainty]

    @computed
    def impact(self) -> float:
        return impact(self.certainty, self.importance.value, self.use.value)


def importance_of(
    genes: Sequence[str], evidence: Sequence[GeneEvidence] | None
) -> Importance:
    if evidence is None:
        return Importance(genes=tuple(genes), source="not_read")
    cited = any(read.pubmed > 0 or read.comments > 0 for read in evidence)
    return Importance(genes=tuple(genes), source="cited" if cited else "uncited")


def use_of(genome: str, *, reference_strain: bool | None) -> GenomeUse:
    match reference_strain:
        case None:
            return GenomeUse(genome=genome, source="unknown", reference=False)
        case True:
            return GenomeUse(genome=genome, source="reference_strain", reference=True)
        case False:
            return GenomeUse(genome=genome, source="other_strain", reference=False)


def use_by_role(genome: str, role: ModelRole) -> GenomeUse:
    return GenomeUse(genome=genome, source="model_role", reference=role == "reference")


def impact(certainty: Certainty, importance: float, use: float) -> float:
    return round(CERTAINTY_WEIGHT[certainty] * importance * use, IMPACT_PLACES)
