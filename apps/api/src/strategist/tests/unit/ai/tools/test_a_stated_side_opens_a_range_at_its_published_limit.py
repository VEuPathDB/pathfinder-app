from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from pydantic_ai.messages import ToolReturn
from veupathdb.domain.parameters import ParamValue, param_value_from_raw
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone._frame_answers import AnsweredRequirement
from strategist.ai.tools.standalone._frame_result import SetCriterionResult
from strategist.ai.tools.standalone.frame_spec import set_criterion
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    CountOp,
    CountValue,
)
from strategist.domain.strategy.operational_spec import BoundValue
from strategist.tests._support.catalog_reads import listing
from strategist.tests._support.recorded_searches import suite_search
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.tools.test_frame_spec import (
    default_why,
    frame_ctx,
    param_info,
    serve_search,
)

_SEARCH = "GenesByIntronJunctions"
_PARAM = "percent_max"


def _range(low: float, high: float) -> ParamValue:
    return param_value_from_raw({"min": low, "max": high}, "number-range")


def _recorded_sheet() -> list[ParameterInfo]:
    return format_param_info_typed(
        suite_search("search_genes_by_intron_junctions").parameters or []
    )


def _no_limit_sheet() -> list[ParameterInfo]:
    return [
        param_info(_PARAM, "number-range", default_value='{"min":"20","max":"28"}'),
    ]


def _no_default_sheet() -> list[ParameterInfo]:
    return [param_info(_PARAM, "number-range", default_value="not a range")]


def _count(op: CountOp, number: float) -> Constraint:
    return Constraint(
        kind=ConstraintKind.COUNT,
        requested_value=f"percent {op} {number}",
        label="percent",
        source=ConstraintSource.USER_EXPLICIT,
        value=CountValue(feature="percent", op=op, value=number),
    )


async def _bound(
    monkeypatch: pytest.MonkeyPatch,
    sheet: list[ParameterInfo],
    proposal: str | None,
    requirements: list[Constraint],
) -> tuple[BoundValue, SetCriterionResult]:
    serve_search(monkeypatch, lambda _context: sheet)
    state = AgentToolState()
    state.stated_requirements = requirements
    state.record_catalog_read(listing([_SEARCH]))
    state.request_messages = ["junction genes"]
    params: dict[str, str | list[str] | None] = {
        info.name: (proposal if info.name == _PARAM else None) for info in sheet
    }
    outcome: ToolReturn[SetCriterionResult] = await set_criterion(
        frame_ctx(state),
        criterion_id="c1",
        text="junction genes",
        search_name=_SEARCH,
        params=params,
        why=default_why(_SEARCH, params),
        answers=[
            AnsweredRequirement(requirement=f"R{i + 1}", param=_PARAM)
            for i in range(len(requirements))
        ],
    )
    [criterion] = state.operational_spec_draft.criteria
    return criterion.resolved_params[_PARAM], returned(outcome, SetCriterionResult)


def test_the_recorded_range_publishes_limits_apart_from_its_default() -> None:
    [info] = [i for i in _recorded_sheet() if i.name == _PARAM]

    assert (info.min, info.max) == (1.0, 100.0)
    assert info.default_value == '{"min":"20","max":"100"}'


@pytest.mark.asyncio
async def test_an_upper_bound_opens_the_low_end_at_the_published_minimum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, result = await _bound(
        monkeypatch,
        _recorded_sheet(),
        '{"min": 20, "max": 50}',
        [_count("<=", 50)],
    )

    assert bound.value == _range(1, 50)
    assert (bound.published_min, bound.published_max) == (1.0, 100.0)
    assert result.corrections == [
        (
            "percent_max binds its low end at the site's published minimum, 1: "
            "the request states no lower bound"
        ),
    ]


@pytest.mark.asyncio
async def test_a_proposal_of_the_stated_end_alone_closes_at_the_published_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, _ = await _bound(
        monkeypatch, _recorded_sheet(), '{"max": 50}', [_count("<=", 50)]
    )

    assert bound.value == _range(1, 50)


@pytest.mark.asyncio
async def test_a_lower_bound_opens_the_high_end_at_the_published_maximum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, result = await _bound(
        monkeypatch,
        _recorded_sheet(),
        '{"min": 30, "max": 90}',
        [_count(">=", 30)],
    )

    assert bound.value == _range(30, 100)
    assert result.corrections == [
        (
            "percent_max binds its high end at the site's published maximum, 100: "
            "the request states no upper bound"
        ),
    ]


@pytest.mark.asyncio
async def test_a_range_stating_both_sides_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, result = await _bound(
        monkeypatch,
        _recorded_sheet(),
        '{"min": 30, "max": 50}',
        [_count(">=", 30), _count("<=", 50)],
    )

    assert bound.value == _range(30, 50)
    assert result.corrections == []


@pytest.mark.asyncio
async def test_a_range_no_requirement_links_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, _ = await _bound(
        monkeypatch, _recorded_sheet(), '{"min": 30, "max": 50}', []
    )

    assert bound.value == _range(30, 50)


@pytest.mark.asyncio
async def test_a_range_left_null_keeps_the_site_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, result = await _bound(
        monkeypatch, _recorded_sheet(), None, [_count("<=", 50)]
    )

    assert bound.value == _range(20, 100)
    assert result.corrections == []


@pytest.mark.asyncio
async def test_with_no_published_limit_the_open_end_keeps_the_site_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, result = await _bound(
        monkeypatch,
        _no_limit_sheet(),
        '{"min": 0, "max": 25}',
        [_count("<=", 25)],
    )

    assert bound.value == _range(20, 25)
    assert result.corrections == [
        (
            "percent_max keeps its low end at the site's default, 20: "
            "the site publishes no minimum and the request states no lower bound"
        ),
    ]


@pytest.mark.asyncio
async def test_a_high_end_with_no_published_limit_keeps_the_site_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, _ = await _bound(
        monkeypatch,
        _no_limit_sheet(),
        '{"min": 22, "max": 40}',
        [_count(">=", 22)],
    )

    assert bound.value == _range(22, 28)


@pytest.mark.asyncio
async def test_a_value_already_at_the_open_end_reports_no_correction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, result = await _bound(
        monkeypatch,
        _recorded_sheet(),
        '{"min": 1, "max": 50}',
        [_count("<=", 50)],
    )

    assert bound.value == _range(1, 50)
    assert result.corrections == []


@pytest.mark.asyncio
async def test_an_open_end_past_the_stated_bound_leaves_the_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, result = await _bound(
        monkeypatch,
        _no_limit_sheet(),
        '{"min": 5, "max": 10}',
        [_count("<=", 10)],
    )

    assert bound.value == _range(5, 10)
    assert result.corrections == []


@pytest.mark.asyncio
async def test_a_default_the_kind_cannot_read_leaves_the_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, result = await _bound(
        monkeypatch,
        _no_default_sheet(),
        '{"min": 5, "max": 10}',
        [_count("<=", 10)],
    )

    assert bound.value == _range(5, 10)
    assert result.corrections == []


@pytest.mark.asyncio
async def test_a_range_with_no_default_and_no_limit_leaves_the_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet = [param_info(_PARAM, "number-range")]

    bound, result = await _bound(
        monkeypatch, sheet, '{"min": 5, "max": 10}', [_count("<=", 10)]
    )

    assert bound.value == _range(5, 10)
    assert result.corrections == []


@pytest.mark.asyncio
async def test_a_range_the_kind_cannot_read_is_left_for_its_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ModelRetry) as retry:
        await _bound(monkeypatch, _recorded_sheet(), "20-28", [_count("<=", 28)])

    assert _PARAM in str(retry.value)


@pytest.mark.asyncio
async def test_a_default_low_end_above_the_stated_high_end_is_not_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bound, result = await _bound(
        monkeypatch, _no_limit_sheet(), '{"max": 10}', [_count("<=", 10)]
    )

    assert bound.value == param_value_from_raw({"max": 10}, "number-range")
    assert result.corrections == []


@pytest.mark.asyncio
async def test_a_range_proposed_with_crossed_ends_is_refused_by_its_kind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ModelRetry) as retry:
        await _bound(
            monkeypatch, _no_limit_sheet(), '{"min": 20, "max": 10}', [_count("<=", 10)]
        )

    assert _PARAM in str(retry.value)


@pytest.mark.asyncio
async def test_a_scalar_parameter_is_never_rewritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sheet = [
        param_info("min_x", "string", is_number=True, default_value="10", min=0),
        param_info(_PARAM, "string", is_number=True, default_value="50", min=1),
    ]
    bound, result = await _bound(monkeypatch, sheet, "30", [_count("<", 30)])

    assert bound.value.to_wire() == "30"
    assert result.corrections == []
