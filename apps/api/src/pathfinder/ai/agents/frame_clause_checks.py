"""What FRAME's requirement reports are held to while a phyletic expression this
conversation built is bound."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import ValidationError
from pydantic_ai import DeferredToolRequests, ModelRetry, RunContext
from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM, PhyleticTree
from veupathdb_mcp.catalog import PhyleticPattern, ortho_taxonomy

from pathfinder.ai.agents.refusal_bound import may_refuse
from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.strategy.expression_handles import bound_patterns
from pathfinder.domain.strategy.pattern_clauses import states_clause
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)

_UNMET = frozenset(
    {RequirementProblem.SITE_HAS_NO_SEARCH, RequirementProblem.STAND_IN_BOUND}
)

type Bound = Sequence[tuple[str, PhyleticPattern]]


def _clauses(reports: list[RequirementReport]) -> dict[str, PhyleticPattern]:
    held: dict[str, PhyleticPattern] = {}
    for report in reports:
        try:
            clause = report.clause_pattern()
        except ValidationError as exc:
            msg = (
                f"The clause of {report.requirement} is no pattern term of "
                f"build_phyletic_expression: {exc.errors()[0]['msg']}. Write it in "
                "that tool's form, or leave the clause out."
            )
            raise ModelRetry(msg) from exc
        if clause is not None:
            held[report.requirement] = clause
    return held


def _stating(clause: PhyleticPattern, bound: Bound, tree: PhyleticTree) -> str | None:
    return next((cid for cid, held in bound if states_clause(held, clause, tree)), None)


def _met_sentence(number: str, clause: PhyleticPattern, criterion_id: str) -> str:
    return (
        f"{number} asks for {clause.outline()}, and {criterion_id} binds an "
        f"expression that states it as a term, so the strategy meets {number}. "
        f"Leave {number} out of requirement_problems."
    )


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
        f"to an expression this conversation built, which reads: {readings}. A "
        "requirement that expression states is met: leave it out of "
        "requirement_problems. A requirement about which genomes hold a group's "
        "proteins that it does not state gives its `clause` as one pattern term. "
        "Send any other report again as it is."
    )


def _without_met(output: FrameResult, met: dict[str, str]) -> FrameResult:
    kept = [r for r in output.requirement_problems if r.requirement not in met]
    return output.model_copy(update={"requirement_problems": kept}).with_gaps(
        [
            PassGap(
                kind="report_dropped",
                sentence=(
                    f"The pass reported {number}, which the expression bound on "
                    f"{cid} states."
                ),
            )
            for number, cid in met.items()
        ]
    )


async def hold_the_reports_to_the_bound_patterns(
    ctx: RunContext[AgentDeps], output: FrameResult | DeferredToolRequests
) -> FrameResult | DeferredToolRequests:
    match output:
        case FrameResult():
            reports = [r for r in output.requirement_problems if r.problem in _UNMET]
        case _:
            return output
    state = ctx.deps.agent_state
    bound = bound_patterns(state.built_expressions, state.operational_spec_draft)
    tree = await ortho_taxonomy(ctx.deps.site_id) if bound and reports else None
    if tree is None:
        return output
    clauses = _clauses(reports)
    met = {
        number: cid
        for number, clause in clauses.items()
        if (cid := _stating(clause, bound, tree)) is not None
    }
    unasked = [
        r
        for r in reports
        if not r.clause.strip() and r.requirement not in state.clause_asked
    ]
    if not (met or unasked) or not may_refuse(ctx, state.refusals):
        return _without_met(output, met) if met else output
    state.refusals += 1
    if met:
        raise ModelRetry(
            " ".join(_met_sentence(n, clauses[n], cid) for n, cid in met.items())
        )
    state.clause_asked |= {r.requirement for r in unasked}
    raise ModelRetry(_ask_sentence(unasked, bound, state))


__all__ = ["hold_the_reports_to_the_bound_patterns"]
