"""A search's published names, and what a reader is never shown."""

from __future__ import annotations

import pytest
from veupathdb.domain import SearchContext
from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb_mcp.catalog import ParameterInfo, SearchParametersResult

from pathfinder.services.experiment import published_names as module

BOOLEAN = "boolean_question_TranscriptRecordClasses_TranscriptRecordClass"


def _answer(display_name: str) -> SearchParametersResult:
    return SearchParametersResult(
        search_name=BOOLEAN,
        display_name=display_name,
        description=None,
        parameters=[
            ParameterInfo(
                name="bq_operator",
                display_name="Operator",
                type="single-pick-vocabulary",
                required=True,
                is_visible=True,
                help="",
                value_format="",
            ),
            ParameterInfo(
                name="unlabelled",
                display_name="",
                type="string",
                required=False,
                is_visible=True,
                help="",
                value_format="",
            ),
        ],
        resolved_record_type="transcript",
    )


async def test_it_reads_the_display_names_wdk_publishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def resolved(ctx: SearchContext) -> SearchParametersResult:
        del ctx
        return _answer("Combine Gene results")

    monkeypatch.setattr(module, "get_search_parameters", resolved)

    names = await module.published_names("plasmodb", "transcript", BOOLEAN)

    assert names.label == "Combine Gene results"
    assert names.parameter_labels == {
        "bq_operator": "Operator",
        "unlabelled": "unlabelled",
    }


async def test_a_url_segment_is_not_a_label(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolved(ctx: SearchContext) -> SearchParametersResult:
        del ctx
        return _answer(BOOLEAN)

    monkeypatch.setattr(module, "get_search_parameters", resolved)

    names = await module.published_names("plasmodb", "transcript", BOOLEAN)

    assert names.label == ""


async def test_a_refused_read_names_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def refused(ctx: SearchContext) -> SearchParametersResult:
        del ctx
        raise VEuPathDBError(VEuPathDBErrorCode.WDK_ERROR, "no such search")

    monkeypatch.setattr(module, "get_search_parameters", refused)

    names = await module.published_names("plasmodb", "transcript", BOOLEAN)

    assert names.label == ""
    assert names.parameter_labels == {}
