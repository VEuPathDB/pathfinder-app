"""The planner's site reads: the site's genomes, the names a request resolves to, and the targets the site can judge."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

import httpx
import pydantic
from assistant_core.platform.logging import get_logger
from veupathdb.errors import VEuPathDBError
from veupathdb.jbrowse import get_jbrowse_client
from veupathdb.wdk import WDKAnswer, get_site
from veupathdb_mcp.audit import (
    GENOME_ATTRIBUTES,
    gene_organism,
    genome_priorities,
    genus_of,
    organism_report,
    provenance_of,
    record_proteins,
    species_of,
)
from veupathdb_mcp.gene_lookup import list_organisms

from pathfinder.domain.audit.planning import (
    PlanRequest,
    RefusedTarget,
    ScopeProposal,
    SiteGenome,
    UnitCosts,
    audited_by_gap,
    comparison_for,
    estimate,
    genome_budget,
    reference_for,
    screened_checks,
)
from pathfinder.domain.audit.scope import (
    AuditScope,
    GenePairTarget,
    GeneTarget,
    MissingGeneTarget,
    OrganelleTarget,
    ScreenedCheck,
    SingleGeneTarget,
)
from pathfinder.platform.config import get_settings

logger = get_logger(__name__)

SEC_PREFILTER = True
SUGGESTIONS = 5
_SERVER_ERROR = 500
MEASURED_COSTS = UnitCosts(
    collect_requests={"audited": 4, "comparison": 1},
    run_requests=1,
    confirm_requests={
        "gene_length": 5,
        "gene_split": 12,
        "pseudogene_call": 4,
        "selenoprotein_end": 9,
        "gene_fusion": 22,
        "strain_model": 10,
        "missing_gene": 8,
        "organelle_join": 6,
        "intron_support": 37,
    },
    evidence_requests={"confirmation": 0, "relatives": 4, "gene_evidence": 3},
    collect_seconds={"audited": 2.2, "comparison": 1.5},
    confirm_seconds={
        "gene_length": 1.7,
        "gene_split": 3.3,
        "pseudogene_call": 3.4,
        "selenoprotein_end": 2.0,
        "gene_fusion": 7.2,
        "strain_model": 3.3,
        "missing_gene": 7.1,
        "organelle_join": 2.4,
        "intron_support": 7.6,
    },
    confirm_store_reads={
        "gene_length": 2,
        "gene_split": 3,
        "pseudogene_call": 5,
        "selenoprotein_end": 3,
        "gene_fusion": 0,
        "strain_model": 6,
        "missing_gene": 6,
        "organelle_join": 6,
        "intron_support": 6,
    },
    evidence_seconds={"confirmation": 0.0, "relatives": 1.3, "gene_evidence": 5.0},
)


def _reference_strain(answer: WDKAnswer, organism: str) -> bool | None:
    try:
        provenance = provenance_of(answer, organism)
    except pydantic.ValidationError:
        return None
    return None if provenance is None else provenance.reference_strain


async def site_organisms(site_id: str) -> tuple[str, ...]:
    return tuple(await list_organisms(site_id))


async def site_genomes(site_id: str) -> list[SiteGenome]:
    organisms = await site_organisms(site_id)
    answer = await organism_report(site_id, GENOME_ATTRIBUTES)
    gaps = {p.organism: p.gap for p in await genome_priorities(site_id)}
    return [
        SiteGenome(
            organism=organism,
            genus=genus_of(organism),
            species=species_of(organism),
            reference_strain=_reference_strain(answer, organism),
            gap=gaps.get(organism),
        )
        for organism in organisms
    ]


def _words(text: str) -> set[str]:
    return set(text.casefold().split())


def _holding(name: str, organisms: Sequence[str]) -> list[str]:
    return [o for o in organisms if _words(name) <= _words(o)]


def _resolved(name: str, organisms: Sequence[str]) -> str | None:
    if name in organisms:
        return name
    folded = [o for o in organisms if o.casefold() == name.casefold()]
    held = folded or _holding(name, organisms)
    return held[0] if len(held) == 1 else None


def _suggestions(name: str, organisms: Sequence[str]) -> tuple[str, ...]:
    return tuple(_holding(name, organisms)[:SUGGESTIONS])


def _placed(target: GeneTarget, placed: dict[str, str]) -> GeneTarget:
    match target:
        case MissingGeneTarget(absent_organism=name):
            return target.model_copy(update={"absent_organism": placed[name]})
        case OrganelleTarget(organism=name):
            return target.model_copy(update={"organism": placed[name]})
        case _:
            return target


type ReadFailure = httpx.TransportError | VEuPathDBError[StrEnum]


def _read_failure(site_id: str, gene: str, error: ReadFailure) -> str:
    logger.warning(
        "Audit plan read failed", site_id=site_id, gene=gene, error=str(error)
    )
    site = get_site(site_id).name
    match error:
        case VEuPathDBError(status=status) if status < _SERVER_ERROR:
            return f"{site} could not read {gene}"
        case _:
            return f"{site} did not answer the read of {gene}"


async def _rna_refusal(site_id: str, gene: str) -> str | None:
    try:
        tracks = await get_jbrowse_client(site_id).junction_tracks(
            await gene_organism(site_id, gene)
        )
    except (httpx.TransportError, VEuPathDBError) as exc:
        return _read_failure(site_id, gene, exc)
    if tracks:
        return None
    site = get_site(site_id).name
    return f"{site} serves no RNA-seq junction track for the genome of {gene}"


async def _sec_refusal(site_id: str, gene: str, reference: str) -> str | None:
    if not SEC_PREFILTER:
        return None
    try:
        proteins = await record_proteins(site_id, [reference])
    except (httpx.TransportError, VEuPathDBError) as exc:
        return _read_failure(site_id, reference, exc)
    protein = proteins.get(reference)
    if protein is None or "U" in protein:
        return None
    return (
        f"the reference protein of {gene} holds no selenocysteine, "
        "so its lineage reads no Sec codon"
    )


async def _refusal(site_id: str, target: GeneTarget) -> str | None:
    match target:
        case SingleGeneTarget(check="intron_support", genes=(gene,)):
            return await _rna_refusal(site_id, gene)
        case GenePairTarget(check="selenoprotein_end", genes=(gene, reference)):
            return await _sec_refusal(site_id, gene, reference)
        case _:
            return None


async def _judged(
    site_id: str, targets: Sequence[GeneTarget]
) -> tuple[tuple[GeneTarget, ...], tuple[RefusedTarget, ...]]:
    kept: list[GeneTarget] = []
    refused: list[RefusedTarget] = []
    for target in targets:
        reason = await _refusal(site_id, target)
        if reason is None:
            kept.append(target)
        else:
            refused.append(RefusedTarget(key=target.key, reason=reason))
    return tuple(kept), tuple(refused)


@dataclass(frozen=True, kw_only=True)
class _GenomePlan:
    genomes: tuple[str, ...] = ()
    comparison: tuple[str, ...] = ()
    checks: tuple[ScreenedCheck, ...] = ()
    reference: str | None = None
    left_out: tuple[str, ...] = ()
    no_reference: str | None = None
    unscreened: str | None = None


def _whole_genomes(count: int) -> str:
    return f"{count} whole genome" if count == 1 else f"{count} whole genomes"


def _target_genomes(targets: Sequence[GeneTarget]) -> frozenset[str]:
    return frozenset(t.whole_genome for t in targets if t.whole_genome is not None)


def _screened(request: PlanRequest, found: str | None) -> tuple[ScreenedCheck, ...]:
    asked = request.checks
    return tuple(c for c in screened_checks(found) if not asked or c in asked)


def _genome_plan(
    request: PlanRequest,
    named: tuple[str, ...],
    genomes: Sequence[SiteGenome],
    targets: Sequence[GeneTarget],
) -> _GenomePlan:
    if not named:
        return _GenomePlan()
    cap = get_settings().audit_max_genomes
    found, why = reference_for(named, genomes)
    read_whole = _target_genomes(targets) & frozenset(named)
    checks: tuple[ScreenedCheck, ...] = _screened(request, found)
    reference = found if "pseudogene_call" in checks else None
    budget = genome_budget(cap, reference=reference, targets=targets, named=named)
    needed = len(read_whole) + int(bool(set(named) - read_whole))
    if reference is not None and budget < needed:
        why = (
            f"the species reference {reference} does not fit the cap of "
            f"{_whole_genomes(cap)}"
        )
        checks = tuple(c for c in checks if c != "pseudogene_call")
        reference = None
        budget = genome_budget(cap, reference=None, targets=targets, named=named)
    if not checks:
        return _GenomePlan(left_out=named, no_reference=why, unscreened=why)
    audited, left_out = audited_by_gap(named, genomes, budget=budget, always=read_whole)
    if not audited:
        return _GenomePlan(left_out=left_out, no_reference=why)
    return _GenomePlan(
        genomes=audited,
        comparison=comparison_for(audited, found, genomes),
        checks=checks,
        reference=reference,
        left_out=left_out,
        no_reference=why,
    )


def plain_problems(error: pydantic.ValidationError) -> str:
    return "; ".join(p["msg"].removeprefix("Value error, ") for p in error.errors())


def _admitted(raw: dict[str, object], cap: int) -> tuple[AuditScope | None, str | None]:
    try:
        return AuditScope.admitted(raw, max_genomes=cap), None
    except pydantic.ValidationError as exc:
        return None, plain_problems(exc)


def _plain_refusal(
    request: PlanRequest, plan: _GenomePlan, targets: tuple[GeneTarget, ...]
) -> str | None:
    if plan.genomes or targets:
        return None
    if plan.unscreened is not None:
        return f"no pseudogene screen can run: {plan.unscreened}"
    if request.targets:
        return "every gene target was refused"
    return None


def _composed(
    request: PlanRequest,
    plan: _GenomePlan,
    targets: tuple[GeneTarget, ...],
    refused: tuple[RefusedTarget, ...],
) -> ScopeProposal:
    settings = get_settings()
    plain = _plain_refusal(request, plan, targets)
    if plain is not None:
        return ScopeProposal(
            request=request,
            left_out=plan.left_out,
            refused_targets=refused,
            no_reference=plan.no_reference,
            refusal=plain,
        )
    raw: dict[str, object] = {
        "siteId": request.site_id,
        "genomes": plan.genomes,
        "comparison": plan.comparison,
        "checks": plan.checks,
        "targets": [t.model_dump(mode="json", by_alias=True) for t in targets],
        "referenceGenome": plan.reference,
    }
    if request.confirm_limit is not None:
        raw["confirmLimit"] = request.confirm_limit
    scope, refusal = _admitted(raw, settings.audit_max_genomes)
    cost = (
        None
        if scope is None
        else estimate(scope, run_hours=settings.audit_run_hours, costs=MEASURED_COSTS)
    )
    return ScopeProposal(
        request=request,
        scope=scope,
        estimate=cost,
        left_out=plan.left_out,
        refused_targets=refused,
        no_reference=plan.no_reference,
        refusal=refusal,
    )


async def propose_scope(request: PlanRequest) -> ScopeProposal:
    genomes = await site_genomes(request.site_id)
    organisms = [genome.organism for genome in genomes]
    places = (t.genome for t in request.targets if t.genome is not None)
    names = tuple(dict.fromkeys((*request.genomes, *places)))
    resolved = {name: _resolved(name, organisms) for name in names}
    placed = {name: o for name, o in resolved.items() if o is not None}
    unresolved = tuple(name for name in names if name not in placed)
    if unresolved:
        return ScopeProposal(
            request=request,
            unresolved=unresolved,
            suggestions={name: _suggestions(name, organisms) for name in unresolved},
        )
    unique: dict[str, GeneTarget] = {}
    for target in request.targets:
        placed_target = _placed(target, placed)
        unique.setdefault(placed_target.key, placed_target)
    targets, refused = await _judged(request.site_id, list(unique.values()))
    cap = get_settings().audit_max_genomes
    reads = len(_target_genomes(targets))
    if reads > cap:
        return ScopeProposal(
            request=request,
            refused_targets=refused,
            refusal=(
                f"the gene targets read {reads} whole genomes, and an audit reads "
                f"at most {cap}"
            ),
        )
    named = tuple(dict.fromkeys(placed[name] for name in request.genomes))
    plan = _genome_plan(request, named, genomes, targets)
    return _composed(request, plan, targets, refused)


async def unresolved_names(scope: AuditScope) -> tuple[str, ...]:
    held = set(await site_organisms(scope.site_id))
    named = (
        *scope.collected,
        scope.reference_genome,
        *(target.genome for target in scope.targets),
    )
    return tuple(
        dict.fromkeys(name for name in named if name is not None and name not in held)
    )
