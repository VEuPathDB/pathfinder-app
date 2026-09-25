"""``set_criterion`` never binds an EDA-backed search: the criterion waits for
the analysis workflow under its own id."""

from __future__ import annotations

import pytest
from pydantic_ai import ModelRetry
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import StringValue
from veupathdb.domain.strategy import StepValidation
from veupathdb.wdk import WDKParameter, WDKSearch, WDKSearchResponse, WDKStringParam
from veupathdb_mcp.catalog import (
    EDA_ANALYSIS_SPEC_PARAM,
    EDA_DATASET_ID_PARAM,
    SUBSET_QUERY,
    ResolvedSearch,
    ValidationCallbacks,
    format_param_info_typed,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.ai.tools.standalone.frame_spec import set_criterion
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.tests._support.catalog_builders import serve_search_details
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    bind,
    frame_ctx,
    genes_by_text,
    serve_definition,
    serve_params,
    serve_resolution,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec_sheet import (
    serve_genes_by_text_definition,
    sheet_call,
)

_DATASET_ID = "DS_70dd50fed7"
_MUTAGENESIS_SEARCH = (
    "GenesByPhenotypeEdaSubset_PlasmoDB_pfal3D7_pB_mutagenesis_MIS_MFS_Phenotype_RSRC"
)
_INVENTED_SPEC = (
    '{"data_type":"read counts",'
    '"comparison":{"case":"febrile","control":"normal"},'
    '"fold_change":{"direction":"both","minimum":2},'
    '"adjusted_p_value":{"maximum":0.05}}'
)


def _eda_params(default: str | None) -> list[WDKParameter]:
    return [
        WDKStringParam(
            name=EDA_DATASET_ID_PARAM,
            display_name=EDA_DATASET_ID_PARAM,
            allow_empty_value=True,
            initial_display_value=default,
        ),
        WDKStringParam(
            name=EDA_ANALYSIS_SPEC_PARAM,
            display_name=EDA_ANALYSIS_SPEC_PARAM,
            allow_empty_value=True,
            initial_display_value="",
        ),
    ]


def _eda_response(default: str | None) -> WDKSearchResponse:
    parameters = _eda_params(default)
    return WDKSearchResponse(
        search_data=WDKSearch(
            url_segment=_MUTAGENESIS_SEARCH,
            display_name=_MUTAGENESIS_SEARCH,
            query_name=SUBSET_QUERY,
            param_names=[p.name for p in parameters],
            parameters=parameters,
        ),
        validation=StepValidation.model_validate(
            {"level": "DISPLAYABLE", "isValid": True, "errors": None}
        ),
    )


def _eda_callbacks(_site_id: str, **_kw: object) -> ValidationCallbacks:
    async def _record_type(
        record_type: str | None, _search_name: str | None
    ) -> str | None:
        return record_type

    async def _hint(_search_name: str, _record_type: str | None) -> str | None:
        return None

    return ValidationCallbacks(
        resolve_record_type_for_search=_record_type, find_record_type_hint=_hint
    )


def _serve_the_eda_search(
    monkeypatch: pytest.MonkeyPatch, *, default: str | None
) -> None:
    """The EDA-backed search, whose dataset default is ``default``."""
    parameters = _eda_params(default)
    infos = format_param_info_typed(parameters)
    serve_params(monkeypatch, lambda _context: infos)
    serve_definition(
        monkeypatch,
        parameters,
        param_names=[p.name for p in parameters],
        query_name=SUBSET_QUERY,
    )
    serve_resolution(
        monkeypatch,
        {
            EDA_DATASET_ID_PARAM: StringValue(value=_DATASET_ID),
            EDA_ANALYSIS_SPEC_PARAM: StringValue(value=_INVENTED_SPEC),
        },
    )

    async def _details(
        ctx: SearchContext, **_kw: object
    ) -> tuple[WDKSearchResponse, str]:
        return _eda_response(default), ctx.record_type

    async def _resolved(_ctx: SearchContext, **_kw: object) -> ResolvedSearch:
        return ResolvedSearch(response=_eda_response(default), values_were_read=True)

    monkeypatch.setattr(frame_spec, "fetch_search_details", _details)
    monkeypatch.setattr(frame_spec, "make_validation_callbacks", _eda_callbacks)
    serve_search_details(monkeypatch, _resolved)


async def _sheet(
    state: AgentToolState,
    *,
    criterion_id: str = "c_essential",
    text: str = "essential in blood stages",
) -> SetCriterionResult:
    return returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id=criterion_id,
            text=text,
            search_name=_MUTAGENESIS_SEARCH,
        ),
        SetCriterionResult,
    )


def _waiting_on(criterion_id: str, text: str, dataset: str) -> Criterion:
    return Criterion(id=criterion_id, text=text, needs_analysis_on=dataset)


def _waiting(criterion_id: str, text: str) -> Criterion:
    return _waiting_on(criterion_id, text, _DATASET_ID)


class TestAnEdaBackedSearchWaitsForItsAnalysis:
    @pytest.fixture(autouse=True)
    def _serve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _serve_the_eda_search(monkeypatch, default=_DATASET_ID)

    async def test_the_sheet_call_is_refused_and_pins_nothing(self) -> None:
        state = AgentToolState()

        with pytest.raises(ModelRetry) as excinfo:
            await _sheet(state)

        message = str(excinfo.value)
        assert _MUTAGENESIS_SEARCH in message
        assert EDA_ANALYSIS_SPEC_PARAM in message
        assert f"needing the analysis workflow on dataset {_DATASET_ID}" in message
        assert "Put c_essential in the structure" in message
        assert "bind no other search for it" in message
        assert state.open_sheets == {}

    async def test_the_criterion_waits_in_the_draft_under_its_own_id(self) -> None:
        state = AgentToolState()

        with pytest.raises(ModelRetry):
            await _sheet(state)

        assert state.operational_spec_draft.criteria == [
            _waiting("c_essential", "essential in blood stages")
        ]
        assert state.operational_spec_draft.dropped == []

    async def test_a_reworded_retry_on_the_same_id_states_one_criterion(self) -> None:
        state = AgentToolState()

        for text in ("essential in blood stages", "essential in blood stages (MIS)"):
            with pytest.raises(ModelRetry):
                await _sheet(state, text=text)

        assert state.operational_spec_draft.criteria == [
            _waiting("c_essential", "essential in blood stages (MIS)")
        ]

    async def test_a_second_comparison_on_the_same_dataset_is_its_own(self) -> None:
        """One dataset answers as many comparisons as the request states."""
        state = AgentToolState()

        with pytest.raises(ModelRetry):
            await _sheet(state, criterion_id="c_24h_vs_18_up", text="24 h over 18 h")
        with pytest.raises(ModelRetry):
            await _sheet(state, criterion_id="c_24h_vs_36_up", text="24 h over 36 h")

        assert state.operational_spec_draft.criteria == [
            _waiting("c_24h_vs_18_up", "24 h over 18 h"),
            _waiting("c_24h_vs_36_up", "24 h over 36 h"),
        ]

    async def test_a_proposed_spec_is_refused_and_binds_nothing(self) -> None:
        state = AgentToolState()

        with pytest.raises(ModelRetry) as excinfo:
            await bind(
                state,
                _MUTAGENESIS_SEARCH,
                {
                    EDA_DATASET_ID_PARAM: _DATASET_ID,
                    EDA_ANALYSIS_SPEC_PARAM: _INVENTED_SPEC,
                },
                criterion_id="c_essential",
                text="essential in blood stages",
            )

        assert "needing the analysis workflow" in str(excinfo.value)
        assert [c.bound for c in state.operational_spec_draft.criteria] == [False]


class TestASearchThatNamesNoDataset:
    @pytest.fixture(autouse=True)
    def _serve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _serve_the_eda_search(monkeypatch, default=None)

    async def test_the_call_asks_for_the_dataset_and_records_nothing(self) -> None:
        state = AgentToolState()

        with pytest.raises(ModelRetry) as excinfo:
            await _sheet(state)

        assert f'params={{"{EDA_DATASET_ID_PARAM}": ' in str(excinfo.value)
        assert state.operational_spec_draft.criteria == []

    async def test_the_named_dataset_is_the_one_it_waits_on(self) -> None:
        state = AgentToolState()

        with pytest.raises(ModelRetry):
            await bind(
                state,
                _MUTAGENESIS_SEARCH,
                {EDA_DATASET_ID_PARAM: _DATASET_ID},
                criterion_id="c_essential",
                text="essential in blood stages",
            )

        assert state.operational_spec_draft.criteria == [
            _waiting("c_essential", "essential in blood stages")
        ]


class TestAPlainSearchStillOpensItsSheet:
    async def test_a_search_without_the_spec_parameter_pins_its_sheet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The refusal reads the parameter, so a classic search is untouched."""
        serve_genes_by_text_definition(monkeypatch)
        serve_params(monkeypatch, genes_by_text)
        state = AgentToolState()

        result = await sheet_call(state)

        assert result.sheet_pinned is True
        assert [entry.name for entry in state.open_sheets["c1"].entries] == [
            "text_expression",
            "text_search_organism",
            "document_type",
            "text_fields",
        ]


class TestAWaitingCriterionKeepsItsDataset:
    _ELSEWHERE = "DS_e973eadd57"

    @pytest.fixture(autouse=True)
    def _serve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _serve_the_eda_search(monkeypatch, default=_DATASET_ID)

    def _state(self, dataset: str) -> AgentToolState:
        state = AgentToolState()
        state.frame_set_criterion(_waiting_on("c_36", "24 h over 36 h", dataset))
        return state

    async def test_the_same_dataset_rewords_it_and_it_still_waits(self) -> None:
        state = self._state(_DATASET_ID)

        with pytest.raises(ModelRetry):
            await _sheet(state, criterion_id="c_36", text="24 h over 36 h, up")

        assert state.operational_spec_draft.criteria == [
            _waiting_on("c_36", "24 h over 36 h, up", _DATASET_ID)
        ]

    async def test_another_dataset_is_refused_and_the_criterion_keeps_its_own(
        self,
    ) -> None:
        state = self._state(self._ELSEWHERE)

        with pytest.raises(ModelRetry) as excinfo:
            await _sheet(state, criterion_id="c_36", text="24 h over 36 h")

        message = str(excinfo.value)
        assert f"waits on dataset {self._ELSEWHERE}" in message
        assert f"runs on dataset {_DATASET_ID}" in message
        assert state.operational_spec_draft.criteria == [
            _waiting_on("c_36", "24 h over 36 h", self._ELSEWHERE)
        ]
