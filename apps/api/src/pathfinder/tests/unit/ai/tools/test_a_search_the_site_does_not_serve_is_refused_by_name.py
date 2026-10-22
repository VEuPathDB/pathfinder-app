from __future__ import annotations

from dataclasses import replace

import pytest
from pydantic_ai import ModelRetry, RunContext
from veupathdb.domain import SearchContext
from veupathdb.errors import ValidationError, WDKError

from pathfinder.ai.agents.frame_result_checks import hold_the_reports_to_the_refusals
from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.unserved import SearchNotServedError
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.requirement_reports import (
    RequirementProblem,
    RequirementReport,
)
from pathfinder.tests._support.catalog_reads import listing
from pathfinder.tests._support.orthomcl_site import TYPED_GENE_ID, recorded_refusal
from pathfinder.tests._support.record_classes import list_searches_under
from pathfinder.tests.unit.ai.tools._orthomcl_site import (
    group_strategy_ctx,
    serve_orthomcl,
)

_TEXT = f"the protein {TYPED_GENE_ID}"
_ANSWER = (
    'HTTP 404 under record type group: There is no search "ByAccession" '
    'associated with record type "GroupRecordClass"'
)
_NOT_SERVED = (
    "The search ByAccession is not served by orthomcl under group (HTTP 404: "
    'There is no search "ByAccession" associated with record type '
    '"GroupRecordClass").'
)
_REFUSAL = (
    f"{_NOT_SERVED} c_protein is not bound, and this pass binds ByAccession no "
    "more. Bind another search for this requirement; a requirement only "
    "ByAccession answers is site_refused_the_search, with ByAccession named."
)


def _stale_catalog(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    list_searches_under(monkeypatch, "group", ["ByAccession"])
    return serve_orthomcl(monkeypatch).reads


async def _name_it(ctx: RunContext[AgentDeps], step: int) -> str:
    with pytest.raises(ModelRetry) as refused:
        await set_criterion(
            replace(ctx, run_step=step, tool_call_id=f"call_{step}"),
            criterion_id="c_protein",
            text=_TEXT,
            search_name="ByAccession",
            role="seed",
            params={"accession": TYPED_GENE_ID} if step % 2 else None,
        )
    return refused.value.message


async def test_a_404_is_recorded_as_the_sites_refusal_of_the_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = _stale_catalog(monkeypatch)
    state = AgentToolState(request_messages=[_TEXT])

    message = await _name_it(group_strategy_ctx(state), 1)

    assert message == _REFUSAL
    assert reads == [("group", "ByAccession")]
    assert state.refused_searches == {"ByAccession": _ANSWER}
    assert state.operational_spec_draft.criteria == []


async def test_a_search_the_site_refused_is_not_asked_for_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads = _stale_catalog(monkeypatch)
    state = AgentToolState(request_messages=[_TEXT])
    ctx = group_strategy_ctx(state)

    messages = [await _name_it(ctx, step) for step in (1, 2)]

    assert messages == [_REFUSAL, _REFUSAL]
    assert reads == [("group", "ByAccession")]


async def test_the_pass_stops_past_the_guards_limit_with_the_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stale_catalog(monkeypatch)
    state = AgentToolState(request_messages=[_TEXT])
    ctx = group_strategy_ctx(state)

    messages = [await _name_it(ctx, step) for step in (1, 2, 3)]
    with pytest.raises(SearchNotServedError) as stopped:
        await set_criterion(
            ctx,
            criterion_id="c_protein",
            text=_TEXT,
            search_name="ByAccession",
            role="seed",
        )

    assert messages == [_REFUSAL] * 3
    assert stopped.value.message == (
        f"{_NOT_SERVED} This pass named a search the site does not serve 4 times "
        "and stops here."
    )


async def test_an_unlisted_name_counts_toward_the_same_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stale_catalog(monkeypatch)
    state = AgentToolState(request_messages=[_TEXT])
    ctx = group_strategy_ctx(state)
    for step in (1, 2):
        await _name_it(ctx, step)
    with pytest.raises(ModelRetry):
        await set_criterion(
            ctx, criterion_id="c_x", text=_TEXT, search_name="ByProteinId"
        )

    with pytest.raises(SearchNotServedError) as stopped:
        await set_criterion(
            ctx, criterion_id="c_y", text=_TEXT, search_name="ByProteinId"
        )

    assert stopped.value.message.startswith(
        "The search ByProteinId is not served by orthomcl under any record type"
    )


async def test_a_404_outside_the_search_lookup_does_not_ban_the_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = serve_orthomcl(monkeypatch)

    async def _refused(_config: object) -> int:
        refusal = WDKError("Not found", status=404)
        raise refusal

    monkeypatch.setattr(site, "create_dataset", _refused)
    state = AgentToolState(request_messages=[_TEXT])
    state.record_catalog_read(listing(["ByIdList"], record_type="sequence"))

    with pytest.raises(WDKError):
        await set_criterion(
            group_strategy_ctx(state),
            criterion_id="c_protein",
            text=_TEXT,
            search_name="ByIdList",
            role="seed",
            params={"source_ids": TYPED_GENE_ID},
        )

    assert state.unserved_searches == {}
    assert state.refused_searches == {}


async def test_the_report_of_the_refused_search_is_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stale_catalog(monkeypatch)
    state = AgentToolState(request_messages=[_TEXT])
    ctx = group_strategy_ctx(state)
    await _name_it(ctx, 1)
    report = FrameResult(
        disposition="needs_user",
        summary="The site refused the protein search.",
        requirement_problems=[
            RequirementReport(
                requirement="R1",
                problem=RequirementProblem.SITE_REFUSED_THE_SEARCH,
                search="ByAccession",
            )
        ],
    )

    assert hold_the_reports_to_the_refusals(ctx, report) is report


async def test_a_404_the_catalog_wraps_is_the_sites_refusal_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stale_catalog(monkeypatch)

    async def _wrapped(ctx: SearchContext, **_kw: object) -> object:
        cause = recorded_refusal(ctx.search_name)
        raise ValidationError(
            title="Search definition could not be read",
            detail=f"reading {ctx.search_name} failed: {cause}",
        ) from cause

    monkeypatch.setattr(frame_spec, "fetch_search_details", _wrapped)
    state = AgentToolState(request_messages=[_TEXT])

    message = await _name_it(group_strategy_ctx(state), 1)

    assert message == _REFUSAL
    assert state.refused_searches == {"ByAccession": _ANSWER}


async def test_a_report_of_an_unlisted_name_is_sent_back_naming_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_orthomcl(monkeypatch)
    state = AgentToolState(request_messages=[_TEXT])
    ctx = group_strategy_ctx(state)
    with pytest.raises(ModelRetry):
        await set_criterion(
            ctx, criterion_id="c_x", text=_TEXT, search_name="ByProteinId"
        )
    report = FrameResult(
        disposition="needs_user",
        summary="The site refused the protein search.",
        requirement_problems=[
            RequirementReport(
                requirement="R1",
                problem=RequirementProblem.SITE_REFUSED_THE_SEARCH,
                search="ByProteinId",
            )
        ],
    )

    with pytest.raises(ModelRetry) as sent_back:
        hold_the_reports_to_the_refusals(ctx, report)

    assert sent_back.value.message == (
        "site_refused_the_search names ['ByProteinId'], which the site's catalog "
        "lists under no record type. A requirement no search on this site answers "
        "is site_has_no_search."
    )
