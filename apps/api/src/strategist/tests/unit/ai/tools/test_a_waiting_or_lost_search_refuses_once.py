from __future__ import annotations

import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKSearch

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone import _frame_sheet, frame_spec
from strategist.ai.tools.standalone._frame_answers import AnsweredRequirement
from strategist.ai.tools.standalone.frame_spec import set_criterion
from strategist.domain.strategy.operational_spec import Criterion
from strategist.platform.refusals import ProblemsRefusal
from strategist.tests.unit.ai.tools.test_every_frame_check_joins_a_stage import (
    _TEXT_CALL,
    _keys,
    _text_call,
    _text_state,
)
from strategist.tests.unit.ai.tools.test_frame_spec import (
    default_why,
    frame_ctx,
    genes_by_text,
    serve_search,
)


def _waiting_on_c1() -> AgentToolState:
    state = _text_state()
    state.frame_set_criterion(
        Criterion(id="c1", text="kinases", needs_analysis_on="DS_70dd50fed7")
    )
    return state


async def test_a_waiting_criterion_on_an_input_path_names_only_its_wait() -> None:
    state = _waiting_on_c1()

    with pytest.raises(ProblemsRefusal) as refused:
        await set_criterion(
            frame_ctx(state),
            criterion_id="c1",
            text="kinases",
            role="transform",
            gene_set="kinases",
            answers=[AnsweredRequirement(requirement="R9", param="nope")],
        )

    assert {key.check for key in _keys(refused.value)} == {"requirements", "waiting"}


async def test_a_waiting_criterion_opening_a_sheet_names_only_its_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _transform(_site_id: str, _record_type: str, name: str) -> WDKSearch:
        return WDKSearch(
            url_segment=name,
            allowed_primary_input_record_class_names=["TranscriptRecordClass"],
        )

    serve_search(monkeypatch, genes_by_text)
    monkeypatch.setattr(_frame_sheet, "read_search_definition", _transform)
    state = _waiting_on_c1()

    with pytest.raises(ProblemsRefusal) as refused:
        await set_criterion(
            frame_ctx(state),
            criterion_id="c1",
            text="kinases",
            search_name="GenesByText",
            role="filter",
        )

    assert {key.check for key in _keys(refused.value)} == {"waiting"}


async def test_an_unknown_requirement_joins_the_missing_search_refusal() -> None:
    with pytest.raises(ProblemsRefusal) as refused:
        await set_criterion(
            frame_ctx(_text_state()),
            criterion_id="c1",
            text="kinases",
            search_name="",
            answers=[AnsweredRequirement(requirement="R9")],
        )

    assert {key.check for key in _keys(refused.value)} == {"requirements", "search"}


async def test_an_unknown_requirement_joins_a_search_the_site_refuses_to_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _not_found(*_args: object) -> WDKSearch:
        msg = "There is no search GenesByText"
        raise WDKError(msg, status=404)

    serve_search(monkeypatch, genes_by_text)
    monkeypatch.setattr(frame_spec, "catalog_search_definition", _not_found)

    refused = await _text_call(
        _text_state(),
        _TEXT_CALL,
        why=default_why("GenesByText", _TEXT_CALL),
        answers=[AnsweredRequirement(requirement="R9")],
    )

    assert {key.check for key in _keys(refused)} == {"requirements", "unserved"}
