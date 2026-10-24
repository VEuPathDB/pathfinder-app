"""A pattern the builder's own guard refuses is named as the builder's limit and
never as a site refusal; a refusal the site answered stays the site's, and data
the site served unreadably is a failed call naming that data."""

from __future__ import annotations

from fractions import Fraction

import pytest
from pydantic_ai import ModelRetry, ToolFailed
from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_SEARCH, PhyleticTree
from veupathdb.errors import DataParsingError, ValidationError, WDKError
from veupathdb_mcp.catalog import (
    AbsentGroupsCompareError,
    PhyleticExpressionResult,
    PhyleticPattern,
)
from veupathdb_mcp.wdk import (
    ComparisonOutOfTimeError,
    ComparisonRequestsError,
    ComputedComparisonResult,
    GenomePastCloudCapError,
    GroupCloudCappedError,
    GroupCloudSumError,
    GroupTagError,
    NestedCompareTooLargeError,
    PerGenomeNeedsTaskError,
)

from pathfinder.ai.agents.frame_result_checks import hold_the_reports_to_the_refusals
from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.tools.standalone import orthomcl_expressions
from pathfinder.ai.tools.standalone.orthomcl_expressions import (
    build_phyletic_expression,
)
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from pathfinder.tests._support.synthetic_taxonomy import pattern, synthetic_tree

from .conftest import agent_run_context

_LIMIT = "The pattern compares 9 distinct sides, more than the call budget allows."
_PRESENT = pattern(
    {
        "kind": "count",
        "of": {"kind": "codes", "codes": ["FERN"]},
        "measure": "genomes",
        "condition": "at_least",
        "value": 1,
    }
)


def _writing(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    async def _tree(site_id: str) -> PhyleticTree | None:
        return synthetic_tree()

    async def _write(
        site_id: str, written: PhyleticPattern
    ) -> PhyleticExpressionResult | ComputedComparisonResult:
        raise error

    monkeypatch.setattr(orthomcl_expressions, "ortho_taxonomy", _tree)
    monkeypatch.setattr(orthomcl_expressions, "answer_phyletic_pattern", _write)


_COMPUTED_LIMITS: list[ValidationError] = [
    AbsentGroupsCompareError("at_least", Fraction(1)),
    NestedCompareTooLargeError(ValidationError(title="Too large", detail=_LIMIT)),
    PerGenomeNeedsTaskError(76, 228),
    ComparisonRequestsError(30, [("tgon", "tgca")]),
    GenomePastCloudCapError("hsap", 12000),
    ComparisonOutOfTimeError(9),
    GroupCloudCappedError(["tgon", "tgca"]),
]
_UNREADABLE: list[DataParsingError] = [
    GroupTagError(["not-a-group"]),
    GroupCloudSumError(120, 118),
]


@pytest.mark.parametrize("limit", _COMPUTED_LIMITS, ids=lambda e: type(e).__name__)
async def test_a_computed_route_limit_is_the_builders_own(
    monkeypatch: pytest.MonkeyPatch, limit: ValidationError
) -> None:
    _writing(monkeypatch, limit)
    state = AgentToolState()

    with pytest.raises(ModelRetry) as refused:
        await build_phyletic_expression(
            agent_run_context(site_id="orthomcl", agent_state=state), _PRESENT
        )

    assert str(refused.value) == (
        f"build_phyletic_expression refused the pattern before the site ran it: "
        f"{limit.detail} This is the builder's own limit, not a site failure: correct "
        "or narrow the pattern and build it again. A requirement no pattern within "
        "the limit states is never site_refused_the_search."
    )
    assert (state.builder_refusals, state.refused_searches) == (
        {PHYLETIC_EXPRESSION_SEARCH: limit.detail},
        {},
    )


@pytest.mark.parametrize("unreadable", _UNREADABLE, ids=lambda e: type(e).__name__)
async def test_an_unreadable_group_cloud_is_a_site_data_failure(
    monkeypatch: pytest.MonkeyPatch, unreadable: DataParsingError
) -> None:
    _writing(monkeypatch, unreadable)
    state = AgentToolState()

    with pytest.raises(ToolFailed) as failed:
        await build_phyletic_expression(
            agent_run_context(site_id="orthomcl", agent_state=state), _PRESENT
        )

    assert str(failed.value) == (
        f"build_phyletic_expression read data the site served that it cannot use "
        f"({unreadable.detail}). Nothing was kept and the strategy is unchanged. Say "
        "that the site's data for this read could not be used, and answer from what "
        "the turn already holds."
    )
    assert (state.refused_searches, state.builder_refusals) == (
        {PHYLETIC_EXPRESSION_SEARCH: unreadable.detail},
        {},
    )


async def test_a_builder_limit_is_named_as_the_builders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _writing(monkeypatch, ValidationError(title="Too large", detail=_LIMIT))
    state = AgentToolState()

    with pytest.raises(ModelRetry) as refused:
        await build_phyletic_expression(
            agent_run_context(site_id="orthomcl", agent_state=state), _PRESENT
        )

    assert str(refused.value) == (
        f"build_phyletic_expression refused the pattern before the site ran it: "
        f"{_LIMIT} This is the builder's own limit, not a site failure: correct or narrow "
        "the pattern and build it again. A requirement no pattern within the limit "
        "states is never site_refused_the_search."
    )
    assert state.builder_refusals == {PHYLETIC_EXPRESSION_SEARCH: _LIMIT}
    assert state.refused_searches == {}


async def test_a_site_refusal_while_building_is_the_sites(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _writing(monkeypatch, WDKError("the count query failed", status=500))
    state = AgentToolState()

    with pytest.raises(ToolFailed):
        await build_phyletic_expression(
            agent_run_context(site_id="orthomcl", agent_state=state), _PRESENT
        )

    assert state.refused_searches == {
        PHYLETIC_EXPRESSION_SEARCH: "HTTP 500: the count query failed"
    }
    assert state.builder_refusals == {}


def test_a_report_of_a_site_refusal_the_builder_made_is_sent_back() -> None:
    state = AgentToolState(builder_refusals={PHYLETIC_EXPRESSION_SEARCH: _LIMIT})
    reported = FrameResult(
        requirement_problems=[
            RequirementReport(
                requirement="R1",
                problem=RequirementProblem.SITE_REFUSED_THE_SEARCH,
                search=PHYLETIC_EXPRESSION_SEARCH,
            )
        ]
    )

    with pytest.raises(ModelRetry) as sent_back:
        hold_the_reports_to_the_refusals(
            agent_run_context(site_id="orthomcl", agent_state=state), reported
        )

    assert str(sent_back.value) == (
        f"site_refused_the_search names ['{PHYLETIC_EXPRESSION_SEARCH}'], and the "
        f"site never ran it: build_phyletic_expression's own limit refused the "
        f"pattern ({_LIMIT}). Narrow the pattern, or report the requirement as "
        "site_has_no_search."
    )
