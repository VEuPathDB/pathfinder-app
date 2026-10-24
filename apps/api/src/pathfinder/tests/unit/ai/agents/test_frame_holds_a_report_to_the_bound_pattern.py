"""FRAME is sent back when it reports a requirement unmet that the bound phyletic
expression states, and asked once for the clause of such a report."""

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
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
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


@pytest.fixture(autouse=True)
def _taxonomy(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _tree(site_id: str) -> PhyleticTree | None:
        return synthetic_tree()

    monkeypatch.setattr(frame_clause_checks, "ortho_taxonomy", _tree)


def _context(refusals: int = 0) -> RunContext[AgentDeps]:
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
            label="where the groups are",
            requested_value="in ferns and in no other plant",
            source=ConstraintSource.USER_EXPLICIT,
        )
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


def _reported(written: PhyleticPattern | None) -> FrameResult:
    return _reported_as("" if written is None else written.model_dump_json())


def _reported_as(clause: str) -> FrameResult:
    return FrameResult(
        requirement_problems=[
            RequirementReport.model_validate(
                {
                    "requirement": "R1",
                    "problem": RequirementProblem.SITE_HAS_NO_SEARCH,
                    "clause": clause,
                }
            )
        ]
    )


async def test_a_report_whose_clause_the_bound_pattern_states_is_sent_back() -> None:
    ctx = _context()

    with pytest.raises(ModelRetry) as sent_back:
        await hold_the_reports_to_the_bound_patterns(ctx, _reported(_ABSENT_ELSEWHERE))

    assert str(sent_back.value) == (
        "R1 asks for at most 0 genomes in MOSS, lna, and c_ferns binds an "
        "expression that states it as a term, so the strategy meets R1. Leave R1 "
        "out of requirement_problems."
    )
    assert ctx.deps.agent_state.refusals == 1


async def test_at_the_bound_a_met_report_is_dropped_with_a_named_gap() -> None:
    held = await hold_the_reports_to_the_bound_patterns(
        _context(refusals=REFUSALS_PER_CHECK), _reported(_ABSENT_ELSEWHERE)
    )

    assert isinstance(held, FrameResult)
    assert held.requirement_problems == []
    assert held.gaps == [
        PassGap(
            kind="report_dropped",
            sentence="The pass reported R1, which the expression bound on c_ferns states.",
        )
    ]


async def test_a_report_whose_clause_the_pattern_does_not_state_stands() -> None:
    reported = _reported(_IN_EVERY_MOSS)

    assert (
        await hold_the_reports_to_the_bound_patterns(_context(), reported) == reported
    )


async def test_a_report_with_no_clause_is_asked_for_one_once() -> None:
    ctx = _context()

    with pytest.raises(ModelRetry) as asked:
        await hold_the_reports_to_the_bound_patterns(ctx, _reported(None))

    assert str(asked.value) == (
        "R1 is reported site_has_no_search while c_ferns binds phyletic_expression "
        "to an expression this conversation built, which reads: in at least 2 "
        "ferns and nowhere else. A requirement that expression states is met: "
        "leave it out of requirement_problems. A requirement about which genomes "
        "hold a group's proteins that it does not state gives its `clause` as one "
        "pattern term. Send any other report again as it is."
    )
    again = _reported(None)
    assert await hold_the_reports_to_the_bound_patterns(ctx, again) == again


async def test_a_clause_that_is_no_pattern_term_is_sent_back() -> None:
    with pytest.raises(ModelRetry) as sent_back:
        await hold_the_reports_to_the_bound_patterns(
            _context(), _reported_as('{"kind": "count", "condition": "absent"}')
        )

    assert str(sent_back.value).startswith(
        "The clause of R1 is no pattern term of build_phyletic_expression: "
    )
