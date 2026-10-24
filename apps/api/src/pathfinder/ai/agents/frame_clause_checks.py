from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from pydantic import ValidationError
from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext
from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM, PhyleticTree
from veupathdb_mcp.catalog import PhyleticPattern, ortho_taxonomy

from pathfinder.ai.agents.refusal_bound import may_refuse
from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.clause_facts import MetClause
from pathfinder.domain.strategy.constraints import Constraint, GenomeShape
from pathfinder.domain.strategy.expression_handles import bound_patterns
from pathfinder.domain.strategy.pattern_clauses import matches_shape, states_clause
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
    numbered_requirements,
)

_UNMET = frozenset(
    {RequirementProblem.SITE_HAS_NO_SEARCH, RequirementProblem.STAND_IN_BOUND}
)

type Bound = Sequence[tuple[str, PhyleticPattern]]


@dataclass
class _Held:
    asks: list[str] = field(default_factory=list)
    gaps: list[PassGap] = field(default_factory=list)
    unasked: list[RequirementReport] = field(default_factory=list)


def _unread(report: RequirementReport, exc: ValidationError) -> tuple[str, PassGap]:
    return (
        (
            f"The clause of {report.requirement} is no pattern term of "
            f"build_phyletic_expression: {exc.errors()[0]['msg']}. Write it in "
            "that tool's form."
        ),
        PassGap(
            kind="clause_unread",
            sentence=f"The clause of {report.requirement} could not be read, so it stands.",
        ),
    )


def _mismatch(
    report: RequirementReport, clause: PhyleticPattern, shape: GenomeShape
) -> tuple[str, PassGap]:
    number = report.requirement
    return (
        (
            f"The clause of {number} is {clause.outline()}, and {number} asks for "
            f"{shape.outline()}. A clause states its own requirement's genomes, "
            "measure and condition."
        ),
        PassGap(
            kind="clause_mismatch",
            sentence=f"The clause of {number} does not state {number}, so it stands.",
        ),
    )


def _met(
    report: RequirementReport,
    held: Constraint,
    clause: PhyleticPattern,
    bound: Bound,
    tree: PhyleticTree,
) -> MetClause | None:
    cid = next((c for c, p in bound if states_clause(p, clause, tree)), None)
    if cid is None:
        return None
    return MetClause(
        number=report.requirement,
        requirement=held.requested_value,
        clause=clause.outline(),
        criterion_id=cid,
    )


def _hold(
    report: RequirementReport,
    held: Constraint,
    shape: GenomeShape,
    found: tuple[Bound, PhyleticTree, AgentToolState, _Held],
) -> None:
    bound, tree, state, out = found
    try:
        clause = report.clause_pattern()
    except ValidationError as exc:
        ask, gap = _unread(report, exc)
        out.asks.append(ask)
        out.gaps.append(gap)
        return
    if clause is None:
        if report.requirement not in state.clause_asked:
            out.unasked.append(report)
        return
    if not matches_shape(clause, shape, tree):
        ask, gap = _mismatch(report, clause, shape)
        out.asks.append(ask)
        out.gaps.append(gap)
        return
    met = _met(report, held, clause, bound, tree)
    if met is not None:
        state.clause_met[met.number] = met


def _ask_sentence(
    unasked: list[RequirementReport], bound: Bound, state: AgentToolState
) -> str:
    named = ", ".join(r.requirement for r in unasked)
    problems = ", ".join(dict.fromkeys(r.problem.value for r in unasked))
    ids = ", ".join(cid for cid, _ in bound)
    readings = "; ".join(
        held.reading
        for held in state.built_expressions.values()
        if any(held.pattern == pattern for _, pattern in bound)
    )
    return (
        f"{named} is reported {problems} while {ids} binds {PHYLETIC_EXPRESSION_PARAM} "
        f"to an expression this conversation built, which reads: {readings}. Give "
        f"the `clause` of {named}: the requirement as one pattern term in "
        "build_phyletic_expression's form, written as JSON."
    )


def _with_met(output: FrameResult, state: AgentToolState) -> FrameResult:
    met = state.clause_met
    if not met:
        return output
    kept = [r for r in output.requirement_problems if r.requirement not in met]
    gaps = [
        PassGap(
            kind="report_dropped",
            sentence=(
                f"The pass reported {m.number}, which the expression bound on "
                f"{m.criterion_id} states as {m.clause}."
            ),
        )
        for m in met.values()
    ]
    return output.model_copy(
        update={"requirement_problems": kept, "met_by_clause": list(met.values())}
    ).with_gaps(gaps)


async def hold_the_reports_to_the_bound_patterns(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    match output:
        case FrameResult():
            reports = [r for r in output.requirement_problems if r.problem in _UNMET]
        case _:
            return output
    state = ctx.deps.agent_state
    numbered = numbered_requirements(state.stated_requirements)
    shaped = [
        (r, held, held.genome_shape)
        for r in reports
        if (held := numbered.get(r.requirement)) is not None
        and held.genome_shape is not None
    ]
    bound = bound_patterns(state.built_expressions, state.operational_spec_draft)
    tree = await ortho_taxonomy(ctx.deps.site_id) if bound and shaped else None
    if tree is None:
        return _with_met(output, state)
    out = _Held()
    for report, held, shape in shaped:
        _hold(report, held, shape, (bound, tree, state, out))
    asks = [
        *out.asks,
        *([_ask_sentence(out.unasked, bound, state)] if out.unasked else []),
    ]
    if asks and may_refuse(ctx, state.refusals):
        state.refusals += 1
        state.clause_asked |= {r.requirement for r in out.unasked}
        raise ModelRetry(" ".join(asks))
    return _with_met(output, state).with_gaps(out.gaps)


__all__ = ["hold_the_reports_to_the_bound_patterns"]
