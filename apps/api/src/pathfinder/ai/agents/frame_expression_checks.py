from __future__ import annotations

from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    PhyleticExpression,
    PhyleticTree,
)
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import ortho_taxonomy

from pathfinder.ai.agents.refusal_bound import may_refuse
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.every_genome import (
    SHARE_PERCENT,
    PresenceReadings,
    UnitReadings,
    asked_units,
    names_genomes,
    presence_readings,
)
from pathfinder.domain.strategy.named_groups import (
    NamedGroup,
    ScopedTaxon,
    scoped_taxa,
    unscoped_taxa,
    whole_taxa,
)
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.requirement_reports import stated_numbers


def _expressions(criteria: list[Criterion]) -> list[tuple[str, PhyleticExpression]]:
    read: list[tuple[str, PhyleticExpression]] = []
    for criterion in criteria:
        bound = criterion.param_values.get(PHYLETIC_EXPRESSION_PARAM)
        if bound is None:
            continue
        try:
            read.append((criterion.id, PhyleticExpression.parse(bound.to_wire())))
        except ValidationError:
            continue
    return read


async def _read_draft(
    ctx: RunContext[AgentDeps], criteria: list[Criterion]
) -> tuple[list[tuple[str, PhyleticExpression]], PhyleticTree] | None:
    read = _expressions(criteria)
    if not read:
        return None
    tree = await ortho_taxonomy(ctx.deps.site_id)
    return None if tree is None else (read, tree)


_READING_COUNTS = {2: "two", 3: "three"}


def _span(unit: UnitReadings) -> str:
    shared = sorted(
        (g for g in unit.species if len(g.genomes) > 1),
        key=lambda g: (-len(g.genomes), g.species),
    )
    named = "".join(f"; {g.species} {len(g.genomes)}" for g in shared)
    return f"{unit.genomes} genomes of {len(unit.species)} species{named}"


def _offered(readings: PresenceReadings) -> list[str]:
    units = readings.units
    offered = [
        " and ".join(f"every one of the {u.genomes} genomes" for u in units)
        + " (recommended)"
    ]
    if readings.share_differs:
        offered.append(
            " and ".join(
                f"at least {u.share} of the {u.genomes} genomes" for u in units
            )
            + f" ({SHARE_PERCENT} percent)"
        )
    if readings.species_differ:
        offered.append(
            " and ".join(f"every one of the {len(u.species)} species" for u in units)
            + ", a species present when at least half its genomes are"
        )
    return offered


def _every_genome_question(criterion_id: str, readings: PresenceReadings) -> str:
    offered = _offered(readings)
    count = _READING_COUNTS[len(offered)]
    return (
        f"{criterion_id} binds {PHYLETIC_EXPRESSION_PARAM} to a presence across "
        f"{' and across '.join(_span(u) for u in readings.units)}, and the "
        f"request names no genome, strain, isolate or proteome. Ask one question on "
        f"{criterion_id}.{PHYLETIC_EXPRESSION_PARAM} with {count} readings from the "
        f"parameter's help, each applied to every list and each label with its "
        f"numbers: {'; '.join(offered)}."
    )


async def hold_an_every_genome_presence_to_a_question(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    if not isinstance(output, FrameResult) or output.disposition != "spec_ready":
        return output
    state = ctx.deps.agent_state
    unasked = [
        criterion
        for criterion in state.operational_spec_draft.criteria
        if criterion.held_reading is None
    ]
    drafted = await _read_draft(ctx, unasked)
    if drafted is None or names_genomes(state.request_messages):
        return output
    read, tree = drafted
    scoped = scoped_taxa(
        state.held_group_scopes,
        output.group_scopes,
        [expression for _, expression in read],
        tree,
    )
    groups = [taxon.required for taxon in whole_taxa(scoped)]
    asked = [
        _every_genome_question(criterion_id, presence_readings(units, tree))
        for criterion_id, expression in read
        if (units := asked_units(expression, tree, groups))
    ]
    if not asked:
        return output
    if not may_refuse(ctx, state.refusals):
        named = [criterion_id for criterion_id, _ in read]
        return output.with_gap(
            "every_genome_unasked",
            f"{', '.join(named)} binds presence across a list of many genomes, and "
            f"the researcher was not asked which presence the request means.",
        )
    state.refusals += 1
    held = ", ".join(stated_numbers(state.stated_requirements))
    keyed = (
        [
            (
                f"Name in the question's `requirements` the keys of the "
                f"requirements its readings approximate, from {held}."
            )
        ]
        if held
        else []
    )
    raise ModelRetry(" ".join([*asked, *keyed, "Absence binds without a question."]))


_LISTED_CODES = 12


def _codes(missing: list[str]) -> str:
    listed = ", ".join(missing[:_LISTED_CODES])
    rest = len(missing) - _LISTED_CODES
    return f"{listed} and {rest} more" if rest > 0 else listed


def _over(
    read: list[tuple[str, PhyleticExpression]], group: NamedGroup, tree: PhyleticTree
) -> str:
    return ", ".join(
        cid
        for cid, expression in read
        if any(tree.genomes_under(u.codes) & group.genomes for u in expression.units())
    )


def _unscoped_gap(group: NamedGroup, ids: str) -> PassGap:
    return PassGap(
        kind="group_scope_missing",
        sentence=(
            f"Scope not stated for {group.name}, so the units of "
            f"{PHYLETIC_EXPRESSION_PARAM} in {ids} are taken as written."
        ),
    )


def _unscoped_ask(group: NamedGroup, ids: str) -> str:
    return (
        f"The units of {PHYLETIC_EXPRESSION_PARAM} in {ids} name more than one "
        f"genome of {group.name}, {len(group.genomes)} genomes, and group_scopes "
        f"states no scope for {group.name}. State one entry with taxon "
        f"{group.taxon!r}: whole when the request means all of it, with "
        f"except_codes for each genome the request leaves out, or named when it "
        f"means exactly the genomes the units name."
    )


def _stated(taxon: ScopedTaxon) -> str:
    return "an earlier pass stated" if taxon.held else "the pass states"


def _short_gap(taxon: ScopedTaxon, ids: str, missing: list[str]) -> PassGap:
    return PassGap(
        kind="group_genomes_left_out",
        sentence=(
            f"{ids} binds {PHYLETIC_EXPRESSION_PARAM} over {taxon.required.name} "
            f"without {_codes(missing)}, and {_stated(taxon)} the whole of it."
        ),
    )


def _short_ask(taxon: ScopedTaxon, ids: str, missing: list[str]) -> str:
    group = taxon.required
    told = f"no unit of {PHYLETIC_EXPRESSION_PARAM} in {ids} names {_codes(missing)}."
    if taxon.held:
        return (
            f"An earlier pass of this request stated all of {group.name}, "
            f"{len(group.genomes)} genomes, in group_scopes, and {told} If the "
            f"request still means all of it, name each of them as present or as "
            f"absent. If it now means only the genomes the units write, restate "
            f"taxon {taxon.group.taxon!r} as named, or as whole with except_codes "
            f"for the genomes it leaves out."
        )
    return (
        f"group_scopes states all of {group.name}, {len(group.genomes)} genomes, "
        f"and {told} Name each of them, as present in the unit that "
        f"stands for its species or its list, or as absent in a unit of its own, "
        f"or list it in except_codes when the request leaves it out; "
        f"lookup_phyletic_codes lists the genomes of each species."
    )


def _stray_gap(taxon: ScopedTaxon) -> PassGap:
    return PassGap(
        kind="group_scope_exception_unknown",
        sentence=(
            f"except_codes of {taxon.group.name} names "
            f"{', '.join(taxon.stray_codes)}, which is no genome of it, so nothing "
            f"is left out for it."
        ),
    )


def _stray_ask(taxon: ScopedTaxon, tree: PhyleticTree) -> str:
    own = [node.code for node in tree.nodes() if node.code in taxon.group.genomes]
    return (
        f"except_codes of taxon {taxon.group.taxon!r} names "
        f"{', '.join(taxon.stray_codes)}, which is no genome of {taxon.group.name}. "
        f"Its genome codes are {_codes(own)}."
    )


async def hold_the_taxa_to_their_scope(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    if not isinstance(output, FrameResult) or output.disposition != "spec_ready":
        return output
    state = ctx.deps.agent_state
    drafted = await _read_draft(ctx, state.operational_spec_draft.criteria)
    if drafted is None:
        return output
    read, tree = drafted
    expressions = [expression for _, expression in read]
    scoped = scoped_taxa(
        state.held_group_scopes, output.group_scopes, expressions, tree
    )
    unscoped = [
        (group, _over(read, group, tree))
        for group in unscoped_taxa(expressions, tree, scoped)
    ]
    stray = [taxon for taxon in scoped if taxon.stray_codes]
    short = [
        (taxon, _over(read, taxon.required, tree), missing)
        for taxon in whole_taxa(scoped)
        if (missing := taxon.required.left_out(expressions, tree))
    ]
    if not unscoped and not stray and not short:
        return output
    if not may_refuse(ctx, state.refusals):
        return output.with_gaps(
            [
                *(_unscoped_gap(group, ids) for group, ids in unscoped),
                *(_stray_gap(taxon) for taxon in stray),
                *(_short_gap(taxon, ids, missing) for taxon, ids, missing in short),
            ]
        )
    state.refusals += 1
    raise ModelRetry(
        " ".join(
            [
                *(_unscoped_ask(group, ids) for group, ids in unscoped),
                *(_stray_ask(taxon, tree) for taxon in stray),
                *(_short_ask(taxon, ids, missing) for taxon, ids, missing in short),
            ]
        )
    )


__all__ = [
    "hold_an_every_genome_presence_to_a_question",
    "hold_the_taxa_to_their_scope",
]
