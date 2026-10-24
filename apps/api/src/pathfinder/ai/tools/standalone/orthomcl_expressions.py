from assistant_core.graph.tool_summary import with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import (
    PhyleticPattern,
    ortho_taxonomy,
    write_phyletic_expression,
)

from pathfinder.ai.capabilities.site_reads import read_in_time
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._expression_handles import held_handle
from pathfinder.domain.strategy.pattern_sets import (
    SetSize,
    counts_beyond_their_sets,
    set_sizes,
)

PHYLETIC_EXPRESSION_MAX_CALL_SECONDS = 300


class BuiltExpression(CamelModel):
    model_config = ConfigDict(frozen=True)

    handle: str
    reading: str
    groups: int
    codes: tuple[str, ...]
    sets: tuple[SetSize, ...] = ()


async def build_phyletic_expression(
    ctx: RunContext[AgentDeps],
    pattern: PhyleticPattern,
) -> ToolReturn[BuiltExpression]:
    """Write OrthoMCL's phyletic_expression from a pattern, check it against the
    site's taxonomy, and count the groups it returns.

    Describe the groups you want; the tool writes the expression. Codes are clade
    or genome codes from lookup_phyletic_codes. A genome with no protein in a group
    counts 0, so at_most and fewer_than include groups absent from the set.

    A pattern is one of these, nested freely:
    - count: {"kind": "count", "of": SET, "measure": M, "condition": C,
      "value": V}. M is genomes (genomes of the set holding a protein), proteins
      (the group's proteins over the set) or share (percent of the set's genomes
      holding a protein). C is at_least, at_most, exactly, more_than or
      fewer_than. {"kind": "count", "of": SET, "condition": "absent"} is no
      protein in any genome of the set, with no measure and no value.
    - compare: {"kind": "compare", "left": SET, "right": SET, "reading": R,
      "condition": C, "factor": F} holds when left C F times right, F defaulting
      to 1. per_genome answers a question about each genome: every genome of
      left against every genome of right. totals answers a question about the
      sets pooled: all proteins of left against all proteins of right. averages
      answers a question about proteins per genome, an average or a ratio: each
      set's proteins divided by its genome count. A comparison of two sets of
      genomes is a compare, never a count over one genome of each.
    - all_of, any_of, none_of: {"kind": "all_of", "terms": [PATTERN, ...]} holds
      when every term holds, any_of when one does, none_of when none does.

    A SET is one of:
    - {"kind": "codes", "codes": ["X"]}: clade X; ["A", "B"] is genomes A and B
      read together; ["ALL"] is every genome.
    - {"kind": "all_except", "codes": ["X"]}: every genome outside clade X.
    - {"kind": "each_species_of", "codes": ["X"]}: the count holds within every
      species of clade X, each on its own.
    - {"kind": "each_genome_of", "codes": ["X"]}: the count holds in every genome
      of clade X, each on its own.
    compare takes codes and all_except only. State a share of a set's genomes
    with measure share: the tool reads each set's genome count from the site's
    taxonomy, and refuses a genome count larger than the set holds. A pattern
    nests at most 8 levels and holds at most 128 terms.

    The result gives handle, reading (the expression in words), groups (the
    groups it returns), codes (the codes it names) and sets (each set the
    pattern names with the genomes its codes cover on the site's taxonomy).
    A genome count you state comes from sets, never from your own count. The expression itself
    stays with the conversation: bind phyletic_expression to the handle, such as
    "expr:3f2a9c01b7de", in this pass or a later one, or offer it as a value of
    a question. A pattern the site could not read or count within the call
    budget is refused with its size; narrow it and call again.

    Args:
        ctx: Agent run context.
        pattern: The groups to select, as described above.
    """
    tree = await ortho_taxonomy(ctx.deps.site_id)
    beyond = [] if tree is None else counts_beyond_their_sets(pattern, tree)
    if beyond:
        raise ModelRetry(" ".join(count.sentence for count in beyond))
    try:
        built = await read_in_time(
            "build_phyletic_expression",
            "the phyletic expression's group counts",
            write_phyletic_expression(ctx.deps.site_id, pattern),
            deadline=PHYLETIC_EXPRESSION_MAX_CALL_SECONDS,
        )
    except ValidationError as exc:
        raise ModelRetry(exc.detail or exc.title) from exc
    held = BuiltExpression(
        handle=held_handle(
            ctx.deps.agent_state, built.expression, pattern, built.reading
        ),
        reading=built.reading,
        groups=built.groups,
        codes=built.codes,
        sets=() if tree is None else set_sizes(pattern, tree),
    )
    return with_summary(held, f"{held.groups} groups", ctx=ctx)
