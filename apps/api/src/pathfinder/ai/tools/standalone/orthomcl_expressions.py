from datetime import UTC, datetime
from typing import Literal

from assistant_core.graph.tool_summary import count_noun, with_summary
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai import ModelRetry, RunContext
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_SEARCH
from veupathdb.errors import DataParsingError, ValidationError, WDKError
from veupathdb_mcp.catalog import (
    PhyleticExpressionResult,
    PhyleticPattern,
    ortho_taxonomy,
)
from veupathdb_mcp.wdk import (
    ComputedComparisonResult,
    ComputedSet,
    answer_phyletic_pattern,
)

from pathfinder.ai.capabilities.site_reads import read_in_time, site_data_failure
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone._expression_handles import held_handle
from pathfinder.domain.strategy.computed_groups import COMPUTED_ROUTE, HeldComparison
from pathfinder.domain.strategy.pattern_sets import (
    SetSize,
    counts_beyond_their_sets,
    set_sizes,
)

PHYLETIC_EXPRESSION_MAX_CALL_SECONDS = 300
_TOOL = "build_phyletic_expression"


class BuiltExpression(CamelModel):
    model_config = ConfigDict(frozen=True)

    route: Literal["expression"] = "expression"
    handle: str
    reading: str
    groups: int
    codes: tuple[str, ...]
    sets: tuple[SetSize, ...] = ()


class ComputedComparison(CamelModel):
    model_config = ConfigDict(frozen=True)

    route: Literal["computed"] = "computed"
    handle: str
    reading: str
    groups: int
    both_held: int
    left_only: int
    right_only: int
    ties: int
    residual_groups: int
    sets: tuple[ComputedSet, ComputedSet]
    probe_requests: int
    compute_requests: int
    fact_id: str
    computed_on: str

    @classmethod
    def of(cls, held: HeldComparison) -> ComputedComparison:
        answer = held.answer
        return cls(
            handle=held.handle,
            reading=answer.reading,
            groups=answer.groups,
            both_held=answer.both_held,
            left_only=answer.left_only,
            right_only=answer.right_only,
            ties=answer.ties,
            residual_groups=answer.residual_groups,
            sets=answer.sets,
            probe_requests=answer.probe_requests,
            compute_requests=answer.compute_requests,
            fact_id=held.fact().id,
            computed_on=held.computed_on.isoformat(),
        )


def _builder_limit(limit: str) -> str:
    return (
        f"build_phyletic_expression refused the pattern before the site ran it: "
        f"{limit} This is the builder's own limit, not a site failure: correct or narrow "
        "the pattern and build it again. A requirement no pattern within the limit "
        "states is never site_refused_the_search."
    )


async def _written(
    ctx: RunContext[AgentDeps], pattern: PhyleticPattern
) -> PhyleticExpressionResult | ComputedComparisonResult:
    refused_searches = ctx.deps.agent_state.refused_searches
    try:
        return await answer_phyletic_pattern(ctx.deps.site_id, pattern)
    except WDKError as refused:
        answer = f"HTTP {refused.status}: {refused.detail}"
        refused_searches[PHYLETIC_EXPRESSION_SEARCH] = answer
        raise
    except DataParsingError as unreadable:
        said = unreadable.detail or unreadable.title
        refused_searches[PHYLETIC_EXPRESSION_SEARCH] = said
        failed = site_data_failure(_TOOL, said)
        raise failed from unreadable


def _computed(
    ctx: RunContext[AgentDeps],
    pattern: PhyleticPattern,
    answer: ComputedComparisonResult,
) -> ToolReturn[BuiltExpression | ComputedComparison]:
    held = HeldComparison(
        pattern=pattern, answer=answer, computed_on=datetime.now(UTC).date()
    )
    ctx.deps.agent_state.computed_comparisons[held.handle] = held
    shown = ComputedComparison.of(held)
    return with_summary(
        shown, f"{count_noun(shown.groups, 'group')}, {COMPUTED_ROUTE}", ctx=ctx
    )


async def build_phyletic_expression(
    ctx: RunContext[AgentDeps],
    pattern: PhyleticPattern,
) -> ToolReturn[BuiltExpression | ComputedComparison]:
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
    A genome count you state comes from sets, never from your own count.
    The expression itself stays with the conversation: bind phyletic_expression to the handle, such as
    "expr:3f2a9c01b7de", in this pass or a later one, or offer it as a value of
    a question. A pattern the site could not read or count within the call
    budget is refused with its size; narrow it and call again.

    A compare that is the whole pattern and whose expression passes the site's
    caps comes back with route "computed": the same groups the expression
    would select, counted from each set's per-group protein counts in at most
    24 requests. It gives groups, bothHeld, leftOnly, rightOnly, ties,
    residualGroups, each set's genomes, species, groups and proteins, the
    requests spent and factId, and holds the group ids under a "groups:"
    handle: pass it to set_criterion as computed_groups to save them as a step,
    a snapshot of today's data the site does not re-run. The computed route
    refuses at_least, at_most and exactly (they hold at 0 against 0); state
    more_than or fewer_than. A per_genome compare that reads more than 24
    requests needs a background task and is refused; compare averages or totals.
    A route "expression" answer is a live search, bound as above.

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
            _written(ctx, pattern),
            deadline=PHYLETIC_EXPRESSION_MAX_CALL_SECONDS,
        )
    except ValidationError as exc:
        limit = exc.detail or exc.title
        ctx.deps.agent_state.builder_refusals[PHYLETIC_EXPRESSION_SEARCH] = limit
        raise ModelRetry(_builder_limit(limit)) from exc
    match built:
        case ComputedComparisonResult():
            return _computed(ctx, pattern, built)
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
