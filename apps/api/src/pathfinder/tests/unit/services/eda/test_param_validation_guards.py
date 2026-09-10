"""Value guards that run before WDK judges: branch expansion and the EDA spec.

Under ``countOnlyLeaves`` WDK scores a branch selection as zero values, so a
branch becomes its leaves first. The ``eda_analysis_spec`` parameter carries a
whole EDA analysis document, so only the values the EDA tools author pass.
"""

from __future__ import annotations

import json
from typing import cast

import pytest
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, JsonValue
from veupathdb.domain.parameters.values import MultiPickValue, ParamValue, StringValue
from veupathdb.domain.search import SearchContext
from veupathdb.eda.models import EdaStringSetFilter
from veupathdb.errors import ValidationError
from veupathdb.wdk.wdk_models import WDKSearchResponse
from veupathdb.wdk.wdk_parameters import (
    WDKEnumParam,
    WDKParameter,
    WDKStringParam,
)
from veupathdb_mcp.catalog import param_validation
from veupathdb_mcp.catalog.eda_backed import (
    COMPUTE_QUERY,
    EDA_ANALYSIS_SPEC_PARAM,
    EDA_DATASET_ID_PARAM,
    SUBSET_QUERY,
)

from pathfinder.services.eda.authoring import new_analysis, serialize_spec
from pathfinder.tests._support.catalog_builders import (
    no_dependent_refresh,
    validation_callbacks,
    wdk_search_response,
)

_PROFILE_CTX = SearchContext(
    site_id="plasmodb", record_type="transcript", search_name="GenesByProfile"
)
_LEAVES = ["17 Hour", "18 Hour", "19 Hour"]
_REJECTS_ZERO = (
    "Number of selected values (0) is not allowed.  Must be within ( 1, unlimited )"
)


def _samples(echoed: str) -> WDKParameter:
    tree: JSONObject = cast(
        "JSONObject",
        {
            "data": {"term": "@@fake@@", "display": "@@fake@@"},
            "children": [
                {
                    "data": {"term": "Trophozoite", "display": "17-30 Hours"},
                    "children": [
                        {"data": {"term": leaf, "display": leaf}} for leaf in _LEAVES
                    ],
                }
            ],
        },
    )
    raw: JSONObject = {
        "type": "multi-pick-vocabulary",
        "name": "samples",
        "display_name": "Samples",
        "display_type": "treeBox",
        "count_only_leaves": True,
        "vocabulary": cast("JsonValue", tree),
        "allow_empty_value": False,
        "initial_display_value": echoed,
    }
    return cast("WDKParameter", WDKEnumParam.model_validate(raw))


def _profile_response(*, rejects_samples: bool, echoed: str) -> WDKSearchResponse:
    return wdk_search_response(
        "GenesByProfile",
        [_samples(echoed)],
        is_valid=not rejects_samples,
        errors=(
            {"general": [], "byKey": {"samples": [_REJECTS_ZERO]}}
            if rejects_samples
            else None
        ),
    )


class _WDK:
    """Rejects a branch selection the way WDK does, and records every ask."""

    def __init__(self) -> None:
        self.asked: list[dict[str, str]] = []

    async def __call__(
        self,
        ctx: SearchContext,
        *,
        resolved_record_type: str,
        parameters: dict[str, ParamValue],
    ) -> param_validation.ResolvedSearch:
        del ctx, resolved_record_type
        sent = param_validation.encode_wdk_params(parameters)
        self.asked.append(sent)
        picked = json.loads(sent.get("samples", "[]"))
        leaf_count = len([v for v in picked if v in _LEAVES])
        # WDK echoes the leaves it read, in its own order.
        return param_validation.ResolvedSearch(
            response=_profile_response(
                rejects_samples=leaf_count == 0,
                echoed=json.dumps(sorted(picked, reverse=True)),
            ),
            values_were_read=True,
        )


@pytest.fixture
def wdk(monkeypatch: pytest.MonkeyPatch) -> _WDK:
    stub = _WDK()
    monkeypatch.setattr(param_validation, "_resolve_search_details", stub)
    monkeypatch.setattr(
        param_validation, "get_refreshed_dependent_params", no_dependent_refresh
    )
    return stub


async def _validate_samples(values: list[str]) -> param_validation.ValidatedParams:
    return await param_validation.validate_parameters(
        _PROFILE_CTX,
        parameters={"samples": MultiPickValue(values=values)},
        callbacks=validation_callbacks(),
    )


class TestABranchTermIsAccepted:
    async def test_it_binds_only_the_parameter_it_was_given(self, wdk: _WDK) -> None:
        del wdk

        assert set((await _validate_samples(["Trophozoite"])).params) == {"samples"}

    async def test_it_becomes_the_leaves(self, wdk: _WDK) -> None:
        del wdk
        result = await _validate_samples(["Trophozoite"])

        assert result.params["samples"] == MultiPickValue(values=_LEAVES)

    async def test_wdk_judges_the_leaves_not_the_branch(self, wdk: _WDK) -> None:
        # WDK counts only leaves, so its verdict on the branch is about a value
        # we were about to replace.
        await _validate_samples(["Trophozoite"])

        assert json.loads(wdk.asked[-1]["samples"]) == _LEAVES

    async def test_the_leaves_are_not_reported_as_substituted(self, wdk: _WDK) -> None:
        # The echo is the same selection in another order, not WDK's own value.
        del wdk

        assert (await _validate_samples(["Trophozoite"])).substituted == []


class TestALeafSelectionIsUnchanged:
    async def test_leaves_pass_straight_through(self, wdk: _WDK) -> None:
        del wdk
        result = await _validate_samples(["17 Hour", "18 Hour"])

        assert result.params["samples"] == MultiPickValue(values=["17 Hour", "18 Hour"])

    async def test_no_second_ask_when_nothing_changed(self, wdk: _WDK) -> None:
        await _validate_samples(["17 Hour", "18 Hour"])

        assert len(wdk.asked) == 1


class TestARealRejectionStillRaises:
    async def test_a_term_in_no_branch_is_reported(self, wdk: _WDK) -> None:
        del wdk
        with pytest.raises(ValidationError):
            await _validate_samples(["99 Hour"])


_DATASET_ID = "DS_e973eadd57"
_DESEQ_SEARCH = "GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq"
_INVENTED_SPEC = (
    '{"data_type":"read counts",'
    '"comparison":{"case":"febrile","control":"normal"},'
    '"fold_change":{"direction":"both","minimum":2},'
    '"adjusted_p_value":{"maximum":0.05}}'
)


class _ErrorRow(BaseModel):
    """One row of a validation error payload."""

    model_config = ConfigDict(extra="ignore")
    param: str
    messages: list[str]


def _authored_spec(dataset_id: str) -> str:
    return serialize_spec(
        new_analysis(
            dataset_id=dataset_id,
            display_name="Febrile against normal",
            filters=[
                EdaStringSetFilter(
                    entity_id="EUPATH_0000096",
                    variable_id="EUPATH_0000731",
                    string_set=["febrile"],
                )
            ],
        )
    )


def _string_param(name: str) -> WDKParameter:
    return WDKStringParam(
        name=name,
        display_name=name,
        allow_empty_value=True,
        initial_display_value="",
    )


def _eda_response(*, search_name: str, query_name: str) -> WDKSearchResponse:
    return wdk_search_response(
        search_name,
        [_string_param(EDA_DATASET_ID_PARAM), _string_param(EDA_ANALYSIS_SPEC_PARAM)],
        level="DISPLAYABLE",
        query_name=query_name,
    )


def _serve(monkeypatch: pytest.MonkeyPatch, response: WDKSearchResponse) -> None:
    async def _details(
        ctx: SearchContext,
        *,
        resolved_record_type: str,
        parameters: dict[str, ParamValue],
    ) -> param_validation.ResolvedSearch:
        del ctx, resolved_record_type, parameters
        return param_validation.ResolvedSearch(response=response, values_were_read=True)

    monkeypatch.setattr(param_validation, "_resolve_search_details", _details)
    monkeypatch.setattr(
        param_validation, "get_refreshed_dependent_params", no_dependent_refresh
    )


async def _validate_spec(
    search_name: str, spec: str
) -> param_validation.ValidatedParams:
    return await param_validation.validate_parameters(
        SearchContext(
            site_id="plasmodb", record_type="transcript", search_name=search_name
        ),
        parameters={
            EDA_DATASET_ID_PARAM: StringValue(value=_DATASET_ID),
            EDA_ANALYSIS_SPEC_PARAM: StringValue(value=spec),
        },
        callbacks=validation_callbacks(),
    )


def _row(exc: ValidationError) -> _ErrorRow:
    errors = exc.errors or []
    assert len(errors) == 1
    return _ErrorRow.model_validate(errors[0])


class TestAProposedSpecIsRefused:
    @pytest.fixture(autouse=True)
    def _compute_search(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _serve(
            monkeypatch,
            _eda_response(search_name=_DESEQ_SEARCH, query_name=COMPUTE_QUERY),
        )

    async def test_the_invented_spec_is_refused(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            await _validate_spec(_DESEQ_SEARCH, _INVENTED_SPEC)

        assert excinfo.value.title == (
            "eda_analysis_spec is written by the host, not proposed"
        )

    async def test_the_refusal_sends_the_model_to_the_eda_tools(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            await _validate_spec(_DESEQ_SEARCH, _INVENTED_SPEC)

        detail = excinfo.value.detail or ""
        assert "open_eda_analysis" in detail
        assert "run_eda_compute" in detail
        assert "create_eda_step" in detail

    async def test_the_refusal_names_the_spec_parameter(self) -> None:
        with pytest.raises(ValidationError) as excinfo:
            await _validate_spec(_DESEQ_SEARCH, _INVENTED_SPEC)

        row = _row(excinfo.value)
        assert row.param == EDA_ANALYSIS_SPEC_PARAM
        assert row.messages

    async def test_a_spec_naming_another_dataset_is_refused(self) -> None:
        with pytest.raises(ValidationError):
            await _validate_spec(_DESEQ_SEARCH, _authored_spec("DS_66f9e70b8a"))

    async def test_a_serialized_analysis_naming_the_dataset_passes(self) -> None:
        result = await _validate_spec(_DESEQ_SEARCH, _authored_spec(_DATASET_ID))

        assert result.params[EDA_ANALYSIS_SPEC_PARAM] == StringValue(
            value=_authored_spec(_DATASET_ID)
        )


class TestAnEmptySpecFollowsTheQuery:
    async def test_the_subset_search_accepts_an_empty_spec(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(
            monkeypatch,
            _eda_response(search_name=SUBSET_QUERY, query_name=SUBSET_QUERY),
        )

        result = await _validate_spec(SUBSET_QUERY, "")

        assert result.params[EDA_ANALYSIS_SPEC_PARAM] == StringValue(value="")

    async def test_a_compute_backed_search_refuses_an_empty_spec(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(
            monkeypatch,
            _eda_response(search_name=COMPUTE_QUERY, query_name=COMPUTE_QUERY),
        )

        with pytest.raises(ValidationError) as excinfo:
            await _validate_spec(COMPUTE_QUERY, "")

        assert "run_eda_compute" in (excinfo.value.detail or "")
        assert _row(excinfo.value).param == EDA_ANALYSIS_SPEC_PARAM


class TestAPlainSearchIsUntouched:
    async def test_a_search_without_the_spec_parameter_validates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(
            monkeypatch,
            wdk_search_response(
                "GenesByText",
                [_string_param("text_expression")],
                level="DISPLAYABLE",
                query_name="GenesByText",
            ),
        )

        result = await param_validation.validate_parameters(
            SearchContext(
                site_id="plasmodb", record_type="transcript", search_name="GenesByText"
            ),
            parameters={"text_expression": StringValue(value="kinase")},
            callbacks=validation_callbacks(),
        )

        assert result.params["text_expression"] == StringValue(value="kinase")
