"""The library's single-gene checks as agent tools, each read recorded as a cite, a fact and the genes it named."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Concatenate

import pydantic
from assistant_core.capabilities.refused_calls import CallRefused
from assistant_core.graph.tool_summary import with_summary
from pydantic import BaseModel, Field
from pydantic_ai import RunContext
from pydantic_ai.messages import ToolReturn
from pydantic_ai.tools import Tool
from pydantic_ai.toolsets.function import FunctionToolset
from veupathdb_mcp.audit import (
    Anatomy,
    GeneEvidence,
    GeneId,
    GeneLengthAudit,
    GenomeProvenance,
    IntronAudit,
    PseudogeneCallAudit,
    RateBounds,
    SelenoproteinEndAudit,
    StrainModelAudit,
)
from veupathdb_mcp.tools import (
    audit_gene_evidence,
    audit_gene_length,
    audit_gene_split,
    audit_genome_provenance,
    audit_intron_support,
    audit_pseudogene_anatomy,
    audit_pseudogene_call,
    audit_selenoprotein_end,
    audit_strain_model,
)

from pathfinder.ai.audit.deps import AuditDeps
from pathfinder.ai.audit.fact_sources import warm_fact_schemas
from pathfinder.ai.audit.facts import (
    AuditRead,
    check_fact,
    genome_records,
    rate_fact,
)
from pathfinder.domain.audit.verdicts import read_cite
from pathfinder.services.audit import investigation
from pathfinder.services.audit.planning import plain_problems

type Count = Annotated[int, Field(ge=0)]


class GeneRead[T](AuditRead[T]):
    genomes: dict[str, str]


async def _recorded[T: BaseModel](
    ctx: RunContext[AuditDeps],
    name: str,
    subjects: tuple[str, ...],
    answer: T,
    *,
    gene_ids: Sequence[GeneId],
    summary: str,
) -> ToolReturn[GeneRead[T]]:
    resolved = tuple(gene_id.resolved for gene_id in gene_ids) or subjects
    known = ctx.deps.record_genomes
    unread = [i.resolved for i in gene_ids if i.resolved not in known]
    known.update(await investigation.gene_genomes(ctx.deps.site_id, unread))
    genomes = {g: known[i.resolved] for i in gene_ids for g in (i.given, i.resolved)}
    ctx.deps.reads |= {read_cite(name, *subjects), read_cite(name, *resolved)}
    ctx.deps.hold_genomes({gene: [genome] for gene, genome in genomes.items()})
    fact = check_fact(name, subjects, answer)
    ctx.deps.facts.append(fact)
    ctx.deps.records.extend(genome_records(ctx.deps.site_id, genomes))
    read = GeneRead[T](answer=answer, fact_id=fact.id, genomes=genomes)
    return with_summary(read, summary, ctx=ctx)


async def audit_gene_length_tool(
    ctx: RunContext[AuditDeps], gene: str
) -> ToolReturn[GeneRead[GeneLengthAudit]]:
    answer = await investigation.gene_length(ctx.deps.site_id, gene)
    return await _recorded(
        ctx,
        "audit_gene_length",
        (gene,),
        answer,
        gene_ids=answer.gene_ids,
        summary=f"{gene}: {answer.length_class}, {answer.verdict}",
    )


async def audit_gene_split_tool(
    ctx: RunContext[AuditDeps], gene_a: str, gene_b: str
) -> ToolReturn[GeneRead[GeneLengthAudit]]:
    answer = await investigation.gene_split(ctx.deps.site_id, gene_a, gene_b)
    return await _recorded(
        ctx,
        "audit_gene_split",
        (gene_a, gene_b),
        answer,
        gene_ids=answer.gene_ids,
        summary=f"{gene_a} and {gene_b}: {answer.length_class}, {answer.verdict}",
    )


async def audit_strain_model_tool(
    ctx: RunContext[AuditDeps], strain_gene: str, reference_gene: str
) -> ToolReturn[GeneRead[StrainModelAudit]]:
    answer = await investigation.strain_model(
        ctx.deps.site_id, strain_gene, reference_gene
    )
    return await _recorded(
        ctx,
        "audit_strain_model",
        (strain_gene, reference_gene),
        answer,
        gene_ids=answer.gene_ids,
        summary=f"{strain_gene} against {reference_gene}: {answer.side}",
    )


async def audit_pseudogene_call_tool(
    ctx: RunContext[AuditDeps], strain_gene: str, reference_gene: str
) -> ToolReturn[GeneRead[PseudogeneCallAudit]]:
    answer = await investigation.pseudogene_call(
        ctx.deps.site_id, strain_gene, reference_gene
    )
    return await _recorded(
        ctx,
        "audit_pseudogene_call",
        (strain_gene, reference_gene),
        answer,
        gene_ids=answer.gene_ids,
        summary=f"{strain_gene} against {reference_gene}: {answer.verdict}",
    )


async def audit_pseudogene_anatomy_tool(
    ctx: RunContext[AuditDeps], strain_gene: str, reference_gene: str
) -> ToolReturn[GeneRead[Anatomy]]:
    answer = await investigation.pseudogene_anatomy(
        ctx.deps.site_id, strain_gene, reference_gene
    )
    return await _recorded(
        ctx,
        "audit_pseudogene_anatomy",
        (strain_gene, reference_gene),
        answer,
        gene_ids=answer.gene_ids,
        summary=f"{strain_gene} against {reference_gene}: {answer.dna_check.verdict}",
    )


async def audit_selenoprotein_end_tool(
    ctx: RunContext[AuditDeps], gene: str, reference_gene: str
) -> ToolReturn[GeneRead[SelenoproteinEndAudit]]:
    answer = await investigation.selenoprotein_end(
        ctx.deps.site_id, gene, reference_gene
    )
    return await _recorded(
        ctx,
        "audit_selenoprotein_end",
        (gene, reference_gene),
        answer,
        gene_ids=answer.gene_ids,
        summary=f"{gene} against {reference_gene}: {answer.verdict}",
    )


async def audit_intron_support_tool(
    ctx: RunContext[AuditDeps], gene: str
) -> ToolReturn[GeneRead[IntronAudit]]:
    answer = await investigation.intron_support(ctx.deps.site_id, gene)
    return await _recorded(
        ctx,
        "audit_intron_support",
        (gene,),
        answer,
        gene_ids=answer.gene_ids,
        summary=f"{gene}: {answer.verdict}",
    )


async def audit_gene_evidence_tool(
    ctx: RunContext[AuditDeps], gene: str
) -> ToolReturn[GeneRead[GeneEvidence]]:
    answer = await investigation.gene_evidence(ctx.deps.site_id, gene)
    return await _recorded(
        ctx,
        "audit_gene_evidence",
        (gene,),
        answer,
        gene_ids=answer.gene_ids,
        summary=f"{gene}: evidence read",
    )


async def audit_genome_provenance_tool(
    ctx: RunContext[AuditDeps], organism: str
) -> ToolReturn[GeneRead[GenomeProvenance]]:
    answer = await investigation.genome_provenance(ctx.deps.site_id, organism)
    return await _recorded(
        ctx,
        "audit_genome_provenance",
        (organism,),
        answer,
        gene_ids=(),
        summary=f"{organism}: provenance read",
    )


async def rate_with_interval(
    ctx: RunContext[AuditDeps], confirmed: Count, checked: Count, unresolved: Count
) -> ToolReturn[AuditRead[RateBounds]]:
    """Compute a rate of confirmed calls over checked calls, with its bounds.

    rate is confirmed over checked. low and high are the Wilson 95% interval
    of that rate. floor and ceiling bound the rate over every call, checked or
    unresolved: floor counts no unresolved call as confirmed, and ceiling
    counts every unresolved call as confirmed. Use it for a count the turn
    read, and state each number it returns by its reference.

    Args:
        confirmed: The calls the check confirmed, at most the checked calls.
        checked: The calls the check judged.
        unresolved: The calls the check could not judge.
    """
    try:
        bounds = investigation.rate_with_interval(confirmed, checked, unresolved)
    except pydantic.ValidationError as exc:
        raise CallRefused(plain_problems(exc)) from exc
    fact = rate_fact(bounds)
    ctx.deps.facts.append(fact)
    return with_summary(
        AuditRead(answer=bounds, fact_id=fact.id),
        f"{confirmed} of {checked} confirmed, {unresolved} unresolved",
        ctx=ctx,
    )


def _turn_site_description(library: Callable[..., object]) -> str:
    lines = (inspect.getdoc(library) or "").splitlines()
    return "\n".join(line for line in lines if not line.strip().startswith("site_id:"))


def _library_tool[**P, R](
    tool: Callable[Concatenate[RunContext[AuditDeps], P], Awaitable[R]],
    library: Callable[..., object],
) -> Tool[AuditDeps]:
    return Tool(
        tool, name=library.__name__, description=_turn_site_description(library)
    )


def build_check_toolset() -> FunctionToolset[AuditDeps]:
    warm_fact_schemas()
    return FunctionToolset(
        [
            _library_tool(audit_gene_length_tool, audit_gene_length),
            _library_tool(audit_gene_split_tool, audit_gene_split),
            _library_tool(audit_strain_model_tool, audit_strain_model),
            _library_tool(audit_pseudogene_call_tool, audit_pseudogene_call),
            _library_tool(audit_pseudogene_anatomy_tool, audit_pseudogene_anatomy),
            _library_tool(audit_selenoprotein_end_tool, audit_selenoprotein_end),
            _library_tool(audit_intron_support_tool, audit_intron_support),
            _library_tool(audit_gene_evidence_tool, audit_gene_evidence),
            _library_tool(audit_genome_provenance_tool, audit_genome_provenance),
            Tool(rate_with_interval),
        ],
        max_retries=3,
    )


CHECK_TOOL_NAMES: frozenset[str] = frozenset(build_check_toolset().tools)
