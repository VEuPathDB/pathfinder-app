"""A report of a requirement the bound phyletic expression states is dropped in
code when its clause states the requirement's own shape; any other clause is
refused within the refusal bound, and the report stands."""

from __future__ import annotations

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.tools import RunContext
from veupathdb.domain.parameters import (
    PHYLETIC_EXPRESSION_PARAM,
    PhyleticTree,
    StringValue,
)
from veupathdb_mcp.catalog import PhyleticPattern

from pathfinder.ai.agents import frame_clause_checks
from pathfinder.ai.agents.frame_clause_checks import (
    hold_the_reports_to_the_bound_patterns,
)
from pathfinder.ai.agents.refusal_bound import REFUSALS_PER_CHECK
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult, PassGap
from pathfinder.domain.clause_facts import MetClause
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    GenomeShape,
)
from pathfinder.domain.strategy.expression_handles import (
    BuiltPattern,
    expression_handle,
)
from pathfinder.domain.strategy.operational_spec import BoundValue, Criterion
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from pathfinder.tests._support.synthetic_taxonomy import pattern, synthetic_tree
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_EXPRESSION = "FERN>=2T AND MOSS+lna=0T"
_ONLY_IN_FERNS = pattern(
    {
        "kind": "all_of",
        "terms": [
            {
                "kind": "count",
                "of": {"kind": "codes", "codes": ["FERN"]},
                "measure": "genomes",
                "condition": "at_least",
                "value": 2,
            },
            {
                "kind": "count",
                "of": {"kind": "all_except", "codes": ["FERN"]},
                "condition": "absent",
            },
        ],
    }
)
_ABSENT_ELSEWHERE = pattern(
    {
        "kind": "count",
        "of": {"kind": "codes", "codes": ["MOSS", "lna"]},
        "measure": "genomes",
        "condition": "at_most",
        "value": 0,
    }
)
_IN_EVERY_MOSS = pattern(
    {
        "kind": "count",
        "of": {"kind": "codes", "codes": ["MOSS"]},
        "measure": "share",
        "condition": "at_least",
        "value": 100,
    }
)
_ABSENT = GenomeShape(condition="absent")
_EVERY = GenomeShape(measure="share", condition="at_least", value=100)
_REQUIREMENT = "in no other plant"
_MET = MetClause(
    number="R1",
    requirement=_REQUIREMENT,
    clause="at most 0 genomes in MOSS, lna",
    criterion_id="c_ferns",
)
_DROPPED = PassGap(
    kind="report_dropped",
    sentence=(
        "The pass reported R1, which the expression bound on c_ferns states as "
        "at most 0 genomes in MOSS, lna."
    ),
)


@pytest.fixture(autouse=True)
def _taxonomy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _tree(site_id: str) -> PhyleticTree | None:
        return synthetic_tree()

    monkeypatch.setattr(frame_clause_checks, "ortho_taxonomy", _tree)


def _context(*shapes: GenomeShape | None, refusals: int = 0) -> RunContext[AgentDeps]:
    ctx = agent_run_context(site_id="orthomcl")
    state = ctx.deps.agent_state
    state.built_expressions[expression_handle(_EXPRESSION)] = BuiltPattern(
        expression=_EXPRESSION,
        pattern=_ONLY_IN_FERNS,
        reading="in at least 2 ferns and nowhere else",
    )
    state.stated_requirements = [
        Constraint(
            kind=ConstraintKind.OTHER,
            label=f"where the groups are {k}",
            requested_value=_REQUIREMENT if k == 0 else f"requirement {k}",
            source=ConstraintSource.USER_EXPLICIT,
            genome_shape=shape,
        )
        for k, shape in enumerate(shapes)
    ]
    state.operational_spec_draft.criteria = [
        Criterion(
            id="c_ferns",
            text="groups only in ferns",
            search_name="GroupsByPhyleticPattern",
            resolved_params={
                PHYLETIC_EXPRESSION_PARAM: BoundValue(
                    value=StringValue(value=_EXPRESSION), source="chosen"
                )
            },
        )
    ]
    state.refusals = refusals
    return ctx


def _report(
    number: str,
    clause: PhyleticPattern | str | None,
    problem: RequirementProblem = RequirementProblem.SITE_HAS_NO_SEARCH,
) -> RequirementReport:
    match clause:
        case None:
            written = ""
        case str():
            written = clause
        case _:
            written = clause.model_dump_json()
    return RequirementReport(requirement=number, problem=problem, clause=written)


def _reported(*reports: RequirementReport) -> FrameResult:
    return FrameResult(requirement_problems=list(reports))


@pytest.mark.parametrize(
    "problem",
    [RequirementProblem.SITE_HAS_NO_SEARCH, RequirementProblem.STAND_IN_BOUND],
)
async def test_a_met_report_is_dropped_in_code_with_its_gap_and_marker(
    problem: RequirementProblem,
) -> None:
    held = await hold_the_reports_to_the_bound_patterns(
        _context(_ABSENT), _reported(_report("R1", _ABSENT_ELSEWHERE, problem))
    )

    assert isinstance(held, FrameResult)
    assert (held.requirement_problems, held.gaps, held.met_by_clause) == (
        [],
        [_DROPPED],
        [_MET],
    )


async def test_a_met_report_is_dropped_after_a_retry_that_left_it_out() -> None:
    ctx = _context(_ABSENT, _EVERY)
    with pytest.raises(ModelRetry):
        await hold_the_reports_to_the_bound_patterns(
            ctx, _reported(_report("R1", _ABSENT_ELSEWHERE), _report("R2", None))
        )

    held = await hold_the_reports_to_the_bound_patterns(
        ctx, _reported(_report("R2", None))
    )

    assert isinstance(held, FrameResult)
    assert (held.gaps, held.met_by_clause) == ([_DROPPED], [_MET])
    assert [r.requirement for r in held.requirement_problems] == ["R2"]


async def test_a_clause_that_does_not_state_its_requirement_is_refused() -> None:
    ctx = _context(_EVERY)

    with pytest.raises(ModelRetry) as sent_back:
        await hold_the_reports_to_the_bound_patterns(
            ctx, _reported(_report("R1", _ABSENT_ELSEWHERE))
        )

    assert str(sent_back.value) == (
        "The clause of R1 is at most 0 genomes in MOSS, lna, and R1 asks for "
        "at_least 100 share over codes. A clause states its own requirement's "
        "genomes, measure and condition."
    )
    assert (ctx.deps.agent_state.refusals, ctx.deps.agent_state.clause_met) == (1, {})


async def test_at_the_bound_a_mismatched_clause_leaves_the_report_standing() -> None:
    report = _report("R1", _ABSENT_ELSEWHERE)

    held = await hold_the_reports_to_the_bound_patterns(
        _context(_EVERY, refusals=REFUSALS_PER_CHECK), _reported(report)
    )

    assert isinstance(held, FrameResult)
    assert (held.requirement_problems, held.gaps, held.met_by_clause) == (
        [report],
        [
            PassGap(
                kind="clause_mismatch",
                sentence="The clause of R1 does not state R1, so it stands.",
            )
        ],
        [],
    )


async def test_a_clause_the_pattern_does_not_state_leaves_the_report() -> None:
    report = _report("R1", _IN_EVERY_MOSS)

    held = await hold_the_reports_to_the_bound_patterns(
        _context(_EVERY), _reported(report)
    )

    assert isinstance(held, FrameResult)
    assert (held.requirement_problems, held.gaps) == ([report], [])


async def test_an_unread_clause_is_refused_within_the_bound() -> None:
    ctx = _context(_ABSENT)

    with pytest.raises(ModelRetry) as sent_back:
        await hold_the_reports_to_the_bound_patterns(
            ctx, _reported(_report("R1", '{"kind": "count", "condition": "absent"}'))
        )

    assert str(sent_back.value).startswith(
        "The clause of R1 is no pattern term of build_phyletic_expression: "
    )
    assert ctx.deps.agent_state.refusals == 1


async def test_at_the_bound_an_unread_clause_leaves_the_report_standing() -> None:
    report = _report("R1", '{"kind": "count", "condition": "absent"}')

    held = await hold_the_reports_to_the_bound_patterns(
        _context(_ABSENT, refusals=REFUSALS_PER_CHECK), _reported(report)
    )

    assert isinstance(held, FrameResult)
    assert (held.requirement_problems, held.gaps) == (
        [report],
        [
            PassGap(
                kind="clause_unread",
                sentence="The clause of R1 could not be read, so it stands.",
            )
        ],
    )


async def test_a_report_with_no_clause_is_asked_for_one_once() -> None:
    ctx = _context(_ABSENT)

    with pytest.raises(ModelRetry) as asked:
        await hold_the_reports_to_the_bound_patterns(
            ctx, _reported(_report("R1", None))
        )

    assert str(asked.value) == (
        "R1 is reported site_has_no_search while c_ferns binds phyletic_expression "
        "to an expression this conversation built, which reads: in at least 2 "
        "ferns and nowhere else. Give the `clause` of R1: the requirement as one "
        "pattern term in build_phyletic_expression's form, written as JSON."
    )
    again = _reported(_report("R1", None))
    assert await hold_the_reports_to_the_bound_patterns(ctx, again) == again


async def test_a_requirement_with_no_shape_keeps_its_report_unasked() -> None:
    reported = _reported(_report("R1", _ABSENT_ELSEWHERE))

    held = await hold_the_reports_to_the_bound_patterns(_context(None), reported)

    assert held == reported
