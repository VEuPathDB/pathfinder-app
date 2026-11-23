from __future__ import annotations

import ast
import inspect
import textwrap

import pytest
from pydantic import JsonValue

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone import frame_spec
from strategist.ai.tools.standalone._frame_answers import AnsweredRequirement
from strategist.ai.tools.standalone.frame_spec import set_criterion
from strategist.domain.refusal import RefusalKey
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.platform.refusals import ProblemsRefusal
from strategist.tests._support.catalog_reads import listing
from strategist.tests._support.param_infos import sheet_of
from strategist.tests.unit.ai.tools.test_frame_reads_a_value_by_its_parameter import (
    _PF,
    _SNPS,
    _every_null,
    _serve,
)
from strategist.tests.unit.ai.tools.test_frame_spec import default_why, frame_ctx

_SEARCH = _SNPS.url_segment
_KINASE = Constraint(
    kind=ConstraintKind.PROPERTY,
    requested_value="SNPs in kinases",
    label="kinase SNPs",
    source=ConstraintSource.USER_EXPLICIT,
)


async def _call(
    state: AgentToolState,
    params: dict[str, JsonValue],
    answers: list[AnsweredRequirement] | None = None,
) -> None:
    state.stated_requirements = [_KINASE]
    state.record_catalog_read(listing([_SEARCH]))
    state.request_messages = state.request_messages or ["SNPs in kinases"]
    await set_criterion(
        frame_ctx(state),
        criterion_id="c_snps",
        text="SNPs in kinases",
        search_name=_SEARCH,
        params=params,
        answers=answers,
        why=default_why(_SEARCH, params),
    )


def _keys(refusal: ProblemsRefusal) -> list[RefusalKey]:
    return [problem.key for problem in refusal.problems.found]


def _required() -> list[str]:
    return sorted(
        info.name
        for info in sheet_of(_SNPS.parameters or [])
        if info.bindable and info.required
    )


async def test_a_name_an_undecided_parameter_and_a_lacked_answer_are_one_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _SNPS)
    params = _every_null(_SNPS)
    del params[_required()[0]]
    params["organsim"] = None
    state = AgentToolState()

    with pytest.raises(ProblemsRefusal) as refused:
        await _call(
            state, params, [AnsweredRequirement(requirement="R1", param="nope")]
        )

    said = str(refused.value)
    assert said.startswith("3 problems:\n1. ")
    assert "organsim" in said
    assert _required()[0] in said
    assert "['nope'], which the sheet does not hold" in said
    assert {key.check for key in _keys(refused.value)} == {
        "answers",
        "unknown_names",
        "undecided",
    }
    assert state.operational_spec_draft.criteria == []


async def test_each_unknown_name_is_offered_its_own_nearest_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _SNPS)
    params = _every_null(_SNPS) | {"organsim": None, "snp_clas": None}

    with pytest.raises(ProblemsRefusal) as refused:
        await _call(AgentToolState(), params)

    unknown = {
        problem.key.parameter: problem.sentence
        for problem in refused.value.problems.found
        if problem.key.check == "unknown_names"
    }
    assert set(unknown) == {"organsim", "snp_clas"}
    assert "snp_class" in unknown["snp_clas"]
    assert "organismSinglePick" in unknown["organsim"]


async def test_a_bad_pick_and_a_bad_number_are_named_in_one_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _SNPS)
    params = _every_null(_SNPS) | {
        "organismSinglePick": [_PF],
        "snp_class": "non-synonymous",
        "ReadFrequencyPercent": "95 percent",
    }
    state = AgentToolState()

    with pytest.raises(ProblemsRefusal) as refused:
        await _call(state, params)

    named = {key.parameter for key in _keys(refused.value)}
    assert {"snp_class", "ReadFrequencyPercent"} <= named
    assert all(
        key
        == RefusalKey(
            check="stated_value",
            criterion="c_snps",
            search=_SEARCH,
            parameter=key.parameter,
        )
        for key in _keys(refused.value)
    )
    assert state.operational_spec_draft.criteria == []


async def test_a_later_stage_waits_for_the_first_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _SNPS)
    params = _every_null(_SNPS) | {
        "organsim": None,
        "snp_class": "non-synonymous",
    }

    with pytest.raises(ProblemsRefusal) as refused:
        await _call(AgentToolState(), params)

    assert {key.check for key in _keys(refused.value)} == {"unknown_names"}


def test_nothing_is_refused_after_the_criterion_is_recorded() -> None:
    source = textwrap.dedent(inspect.getsource(frame_spec._bind_the_search))
    body = ast.parse(source).body[0]
    assert isinstance(body, ast.AsyncFunctionDef)
    recorded = next(
        index
        for index, statement in enumerate(body.body)
        if "record_bound_criterion" in ast.unparse(statement)
    )

    after = [ast.unparse(statement) for statement in body.body[recorded + 1 :]]

    assert after
    assert not [line for line in after if "raise" in line or "Refusal" in line]
