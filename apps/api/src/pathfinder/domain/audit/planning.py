"""The planner's pure rules: which genomes an audit reads, what it checks, what it costs, and the card a start asks on."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Self, get_args

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field, field_validator, model_validator

from pathfinder.domain.audit.findings import EvidenceKind
from pathfinder.domain.audit.scope import (
    MAX_COMPARISON_GENOMES,
    MAX_CONFIRM_LIMIT,
    MAX_TARGETS,
    AuditScope,
    CheckName,
    GeneTarget,
    GenomeRole,
    OrganismName,
    ScreenedCheck,
)
from pathfinder.domain.audit.verdicts import AGREEMENT_SAMPLE, MAX_REVIEWS_PER_RUN

START_LABEL = "Start this audit?"
EVIDENCE_KINDS: Mapping[CheckName, tuple[EvidenceKind, ...]] = {
    check: ("relatives", "gene_evidence")
    if check in {"gene_length", "gene_split"}
    else ("gene_evidence",)
    for check in get_args(CheckName)
}


class SiteGenome(CamelModel):
    model_config = ConfigDict(frozen=True)

    organism: OrganismName
    genus: str
    species: str
    reference_strain: bool | None
    gap: float | None


class PlanRequest(CamelModel):
    model_config = ConfigDict(frozen=True)

    site_id: str = Field(min_length=1)
    genomes: tuple[str, ...] = ()
    checks: tuple[ScreenedCheck, ...] | None = None
    targets: tuple[GeneTarget, ...] = ()
    confirm_limit: int | None = None

    @field_validator("checks")
    @classmethod
    def _some_check(
        cls, checks: tuple[ScreenedCheck, ...] | None
    ) -> tuple[ScreenedCheck, ...] | None:
        if checks == ():
            msg = (
                "an audit request names at least one check, or leaves the checks "
                "to the planner"
            )
            raise ValueError(msg)
        return checks

    @field_validator("targets")
    @classmethod
    def _at_most_the_targets(
        cls, targets: tuple[GeneTarget, ...]
    ) -> tuple[GeneTarget, ...]:
        if len(targets) > MAX_TARGETS:
            msg = f"an audit checks at most {MAX_TARGETS} gene targets, not {len(targets)}"
            raise ValueError(msg)
        return targets

    @field_validator("confirm_limit")
    @classmethod
    def _a_limit_it_confirms(cls, limit: int | None) -> int | None:
        if limit is not None and not 1 <= limit <= MAX_CONFIRM_LIMIT:
            msg = (
                f"an audit confirms between 1 and {MAX_CONFIRM_LIMIT} findings "
                f"for each check, not {limit}"
            )
            raise ValueError(msg)
        return limit


class RefusedTarget(CamelModel):
    model_config = ConfigDict(frozen=True)

    key: str
    reason: str


class RunEstimate(CamelModel):
    model_config = ConfigDict(frozen=True)

    wdk_requests: int = Field(ge=0)
    store_reads: int = Field(ge=0)
    hours: float = Field(ge=0)
    hours_at_most: float = Field(gt=0)
    model_reviews: int = Field(ge=0)
    datasets: int = Field(ge=0, le=1)


def _unnamed(field: str, held: Collection[str], keys: tuple[str, ...]) -> list[str]:
    return [f"{field} names no {key}" for key in keys if key not in held]


class UnitCosts(CamelModel):
    model_config = ConfigDict(frozen=True)

    collect_requests: Mapping[GenomeRole, int]
    run_requests: int = Field(ge=0)
    list_requests: int = Field(ge=0)
    confirm_requests: Mapping[CheckName, int]
    evidence_requests: Mapping[EvidenceKind, int]
    collect_seconds: Mapping[GenomeRole, float]
    confirm_seconds: Mapping[CheckName, float]
    confirm_store_reads: Mapping[CheckName, int]
    evidence_seconds: Mapping[EvidenceKind, float]
    model_reads_per_finding: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _every_unit(self) -> Self:
        roles: tuple[str, ...] = get_args(GenomeRole)
        checks: tuple[str, ...] = get_args(CheckName)
        kinds: tuple[str, ...] = get_args(EvidenceKind)
        missing = [
            *_unnamed("collect_requests", self.collect_requests, roles),
            *_unnamed("collect_seconds", self.collect_seconds, roles),
            *_unnamed("confirm_requests", self.confirm_requests, checks),
            *_unnamed("confirm_seconds", self.confirm_seconds, checks),
            *_unnamed("confirm_store_reads", self.confirm_store_reads, checks),
            *_unnamed("evidence_requests", self.evidence_requests, kinds),
            *_unnamed("evidence_seconds", self.evidence_seconds, kinds),
        ]
        if missing:
            raise ValueError("; ".join(missing))
        return self


class ScopeProposal(CamelModel):
    model_config = ConfigDict(frozen=True)

    request: PlanRequest
    scope: AuditScope | None = None
    estimate: RunEstimate | None = None
    left_out: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    suggestions: dict[str, tuple[str, ...]] = Field(default_factory=dict)
    refused_targets: tuple[RefusedTarget, ...] = ()
    no_reference: str | None = None
    refusal: str | None = None

    @model_validator(mode="after")
    def _scope_and_estimate_together(self) -> Self:
        if (self.scope is None) != (self.estimate is None):
            msg = "a proposal carries a scope and its estimate together"
            raise ValueError(msg)
        return self


class AuditStartCard(CamelModel):
    model_config = ConfigDict(frozen=True)

    tool_call_id: str
    site_id: str
    genomes: tuple[str, ...]
    comparison: tuple[str, ...]
    reference_genome: str | None
    checks: tuple[CheckName, ...]
    targets: int
    left_out: tuple[str, ...]
    refused_targets: tuple[RefusedTarget, ...]
    wdk_requests: int
    store_reads: int
    hours: float
    hours_at_most: float
    model_reviews: int
    datasets: int


def _by_name(genomes: Sequence[SiteGenome]) -> dict[str, SiteGenome]:
    return {genome.organism: genome for genome in genomes}


def genome_budget(
    cap: int,
    *,
    reference: str | None,
    targets: Sequence[GeneTarget],
    named: Sequence[str],
) -> int:
    read = {reference, *(target.whole_genome for target in targets)}
    unnamed = {name for name in read if name is not None and name not in named}
    return max(0, cap - len(unnamed))


def audited_by_gap(
    named: Sequence[str],
    genomes: Sequence[SiteGenome],
    *,
    budget: int,
    always: frozenset[str] = frozenset(),
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if len(named) <= budget:
        return tuple(named), ()
    known = _by_name(genomes)
    gaps = {name: known[name].gap if name in known else None for name in named}
    fixed = [name for name in named if name in always]
    ranked = sorted(
        (name for name in named if name not in always),
        key=lambda name: (gaps[name] is None, -(gaps[name] or 0.0), name),
    )
    room = max(0, budget - len(fixed))
    return (*fixed, *ranked[:room]), tuple(sorted(ranked[room:]))


def reference_for(
    named: Sequence[str], genomes: Sequence[SiteGenome]
) -> tuple[str | None, str | None]:
    known = _by_name(genomes)
    species = sorted({known[name].species for name in named if name in known})
    if len(species) != 1:
        return None, f"the named genomes span {len(species)} species"
    marked = [
        g.organism
        for g in genomes
        if g.species == species[0] and g.reference_strain is True
    ]
    audited = [name for name in marked if name in named]
    if audited:
        return None, f"the named genomes include the species reference {audited[0]}"
    if not marked:
        return None, f"no genome of {species[0]} is marked a reference strain"
    if len(marked) > 1:
        return (
            None,
            f"{len(marked)} genomes of {species[0]} are marked reference strains",
        )
    return marked[0], None


def comparison_for(
    audited: Sequence[str], reference: str | None, genomes: Sequence[SiteGenome]
) -> tuple[str, ...]:
    known = _by_name(genomes)
    genera = {known[name].genus for name in audited if name in known}
    species = {known[name].species for name in audited if name in known}
    relatives = [g for g in genomes if g.genus in genera and g.organism not in audited]
    ranked = sorted(
        relatives,
        key=lambda g: (
            g.organism != reference,
            g.reference_strain is not True,
            g.species not in species,
        ),
    )
    return tuple(g.organism for g in ranked)[:MAX_COMPARISON_GENOMES]


def screened_checks(reference: str | None) -> tuple[ScreenedCheck, ...]:
    if reference is None:
        return ("gene_length", "gene_split")
    return ("gene_length", "gene_split", "pseudogene_call")


def _units(scope: AuditScope) -> list[tuple[CheckName, int]]:
    screened: list[tuple[CheckName, int]] = [
        (check, scope.confirm_limit) for _ in scope.genomes for check in scope.checks
    ]
    return [*screened, *((target.check, 1) for target in scope.targets)]


def _finding_requests(check: CheckName, costs: UnitCosts) -> int:
    evidence = sum(costs.evidence_requests[kind] for kind in EVIDENCE_KINDS[check])
    return costs.confirm_requests[check] + costs.model_reads_per_finding + evidence


def _finding_seconds(check: CheckName, costs: UnitCosts) -> float:
    evidence = sum(costs.evidence_seconds[kind] for kind in EVIDENCE_KINDS[check])
    return costs.confirm_seconds[check] + evidence


def lists_targets(scope: AuditScope) -> bool:
    return any(target.genome is None for target in scope.targets)


def estimate(scope: AuditScope, *, run_hours: float, costs: UnitCosts) -> RunEstimate:
    units = _units(scope)
    listed = lists_targets(scope)
    roles: list[GenomeRole] = [role for _, role in scope.roles]
    requests = (
        sum(costs.collect_requests[role] for role in roles)
        + costs.run_requests
        + (costs.list_requests if listed else 0)
        + sum(n * _finding_requests(check, costs) for check, n in units)
    )
    seconds = sum(costs.collect_seconds[role] for role in roles) + sum(
        n * _finding_seconds(check, costs) for check, n in units
    )
    return RunEstimate(
        wdk_requests=requests,
        store_reads=sum(n * costs.confirm_store_reads[check] for check, n in units),
        hours=seconds / 3600,
        hours_at_most=run_hours,
        model_reviews=MAX_REVIEWS_PER_RUN + AGREEMENT_SAMPLE,
        datasets=int(listed),
    )


def start_card(proposal: ScopeProposal, *, tool_call_id: str) -> AuditStartCard:
    scope, cost = proposal.scope, proposal.estimate
    if scope is None or cost is None:
        msg = "a proposal with no scope draws no start card"
        raise ValueError(msg)
    return AuditStartCard(
        tool_call_id=tool_call_id,
        site_id=scope.site_id,
        genomes=scope.genomes,
        comparison=scope.comparison,
        reference_genome=scope.reference_genome,
        checks=tuple(sorted({*scope.checks, *(t.check for t in scope.targets)})),
        targets=len(scope.targets),
        left_out=proposal.left_out,
        refused_targets=proposal.refused_targets,
        wdk_requests=cost.wdk_requests,
        store_reads=cost.store_reads,
        hours=cost.hours,
        hours_at_most=cost.hours_at_most,
        model_reviews=cost.model_reviews,
        datasets=cost.datasets,
    )


def same_scope(a: AuditScope, b: AuditScope) -> bool:
    def unordered(scope: AuditScope) -> tuple[object, ...]:
        return (
            scope.site_id,
            frozenset(scope.genomes),
            frozenset(scope.comparison),
            frozenset(scope.checks),
            frozenset(target.key for target in scope.targets),
            scope.reference_genome,
            scope.confirm_limit,
        )

    return unordered(a) == unordered(b)
