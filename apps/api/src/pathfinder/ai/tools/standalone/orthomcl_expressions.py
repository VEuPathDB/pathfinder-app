from assistant_core.graph.tool_summary import with_summary
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.errors import ValidationError
from veupathdb_mcp import catalog
from veupathdb_mcp.catalog import (
    CladeOnlyExpression,
    EverySpeciesExpression,
    ProteinCountComparison,
)

from pathfinder.ai.capabilities.site_reads import read_in_time
from pathfinder.ai.graph.runtime import AgentDeps

PROTEIN_COMPARISON_MAX_CALL_SECONDS = 120


async def build_protein_count_comparison(
    ctx: RunContext[AgentDeps],
    genome_a: str,
    genome_b: str,
    reverse: bool = False,
) -> ToolReturn[ProteinCountComparison]:
    """Build the OrthoMCL phyletic_expression for the groups in which genome A
    holds more proteins than genome B, and count the groups it returns.

    The expression is B=0 AND A>=1 OR B=1 AND A>=2 OR ... OR B=K AND A>=K+1,
    where K is the smallest count for which B>=K+1 returns no group. K is read
    from the site with at most 15 count reports. Each ladder gives its
    expression, the groups it returns, and length, its characters; the
    parameter has no length limit, so bind the expression whole. A group with
    as many proteins in both genomes is in neither ladder. A genome B with 1024
    or more proteins in one group is refused.

    Args:
        ctx: Agent run context.
        genome_a: Genome A, one genome code (leaf=true in lookup_phyletic_codes).
        genome_b: Genome B, one genome code (leaf=true in lookup_phyletic_codes).
        reverse: Also build the ladder of the groups in which genome B holds
            more proteins than genome A.
    """
    try:
        comparison = await read_in_time(
            "build_protein_count_comparison",
            f"the protein counts of {genome_a} and {genome_b}",
            catalog.compare_protein_counts(
                ctx.deps.site_id, genome_a, genome_b, reverse=reverse
            ),
            deadline=PROTEIN_COMPARISON_MAX_CALL_SECONDS,
        )
    except ValidationError as exc:
        raise ModelRetry(exc.detail or exc.title) from exc
    return with_summary(
        comparison,
        "; ".join(
            f"{ladder.groups} groups with more proteins in {ladder.more} than "
            f"{ladder.fewer}"
            for ladder in comparison.ladders
        ),
        ctx=ctx,
    )


async def build_clade_only_expression(
    ctx: RunContext[AgentDeps],
    clade: list[str],
    within: list[str] | None = None,
) -> ToolReturn[CladeOnlyExpression]:
    """Build the OrthoMCL phyletic_expression for the groups present in a clade
    L and in no genome outside it, and count the groups it returns.

    The expression is L>=1T AND C=0T, with C every genome outside L, written
    from the site's taxonomy: a clade code for each whole clade outside L and a
    genome code for the rest. With within, a clade M that holds every genome of
    L, C is every genome outside M, so the groups may also hold proteins
    elsewhere in M. The result gives expression, groups, length, its
    characters, genomes, the genome codes of L, and outside, the number of
    genomes C covers; the parameter has no length limit, so bind the expression
    whole. For a clade X whose genomes must hold no protein, write L>=1T AND
    X=0T instead.

    Args:
        ctx: Agent run context.
        clade: L, one clade code, or the genome codes of a group with no clade
            code of its own, such as a genus, from lookup_phyletic_codes.
        within: M, the codes of a clade that holds every genome of L; every
            genome outside M must hold no protein.
    """
    try:
        built = await catalog.clade_only_expression(ctx.deps.site_id, clade, within)
    except ValidationError as exc:
        raise ModelRetry(exc.detail or exc.title) from exc
    return with_summary(
        built,
        f"{built.groups} groups with a protein in {len(built.genomes)} genomes and "
        f"none in {built.outside} others",
        ctx=ctx,
    )


async def build_every_species_expression(
    ctx: RunContext[AgentDeps],
    clade: list[str],
) -> ToolReturn[EverySpeciesExpression]:
    """Build the OrthoMCL phyletic_expression for the groups present in every
    species of a clade L, and count the groups it returns.

    A group is present in a species S of k genomes when at least ceil(k/2) of
    those genomes hold a protein of the group, the unit S>=ceil(k/2)T; a species
    of one genome is S>=1T. The expression joins one unit per species of L with
    AND, written from the site's taxonomy. The result gives expression, groups,
    length, its characters, genomes, the genome codes of L, and species, each
    species with its genomes and present, the genomes that must hold a protein;
    the parameter has no length limit, so bind the expression whole. For
    presence in every genome write L=NT instead, and for presence in some genome
    L>=1T. A clade of one species is refused.

    Args:
        ctx: Agent run context.
        clade: L, one clade code, or the genome codes of a group with no clade
            code of its own, such as a genus, from lookup_phyletic_codes.
    """
    try:
        built = await catalog.every_species_expression(ctx.deps.site_id, clade)
    except ValidationError as exc:
        raise ModelRetry(exc.detail or exc.title) from exc
    return with_summary(
        built,
        f"{built.groups} groups present in each of {len(built.species)} species",
        ctx=ctx,
    )
