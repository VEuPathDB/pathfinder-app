"""The library's single-gene checks an agent may run in a conversation, and the rate interval it may compute."""

from __future__ import annotations

from collections.abc import Iterable

from veupathdb_mcp.audit import (
    Anatomy,
    GeneEvidence,
    GeneLengthAudit,
    GenomeProvenance,
    IntronAudit,
    PseudogeneCallAudit,
    RateBounds,
    SelenoproteinEndAudit,
    StrainModelAudit,
    gene_organism,
    rate_with_bounds,
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


async def gene_length(site_id: str, gene: str) -> GeneLengthAudit:
    return await audit_gene_length(site_id, gene)


async def gene_split(site_id: str, gene_a: str, gene_b: str) -> GeneLengthAudit:
    return await audit_gene_split(site_id, gene_a, gene_b)


async def strain_model(
    site_id: str, strain_gene: str, reference_gene: str
) -> StrainModelAudit:
    return await audit_strain_model(site_id, strain_gene, reference_gene)


async def pseudogene_call(
    site_id: str, strain_gene: str, reference_gene: str
) -> PseudogeneCallAudit:
    return await audit_pseudogene_call(site_id, strain_gene, reference_gene)


async def pseudogene_anatomy(
    site_id: str, strain_gene: str, reference_gene: str
) -> Anatomy:
    return await audit_pseudogene_anatomy(site_id, strain_gene, reference_gene)


async def selenoprotein_end(
    site_id: str, gene: str, reference_gene: str
) -> SelenoproteinEndAudit:
    return await audit_selenoprotein_end(site_id, gene, reference_gene)


async def intron_support(site_id: str, gene: str) -> IntronAudit:
    return await audit_intron_support(site_id, gene)


async def gene_evidence(site_id: str, gene: str) -> GeneEvidence:
    return await audit_gene_evidence(site_id, gene)


async def genome_provenance(site_id: str, organism: str) -> GenomeProvenance:
    return await audit_genome_provenance(site_id, organism)


def rate_with_interval(confirmed: int, checked: int, unresolved: int) -> RateBounds:
    return rate_with_bounds(confirmed, checked, unresolved)


async def gene_genomes(site_id: str, genes: Iterable[str]) -> dict[str, str]:
    return {gene: await gene_organism(site_id, gene) for gene in dict.fromkeys(genes)}
