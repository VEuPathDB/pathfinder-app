"""``set_criterion`` refuses an EDA-backed search on both of its calls."""

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
from pathfinder.ai.tools.standalone._frame_eda import EDA_DROP_REASON
from pathfinder.ai.tools.standalone.frame_spec import SetCriterionResult, set_criterion
from pathfinder.domain.strategy.operational_spec import Criterion, DroppedCriterion
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
_EDA_PARAMS: list[WDKParameter] = [
    WDKStringParam(
        name=EDA_DATASET_ID_PARAM,
        display_name=EDA_DATASET_ID_PARAM,
        allow_empty_value=True,
        initial_display_value=_DATASET_ID,
    ),
    WDKStringParam(
        name=EDA_ANALYSIS_SPEC_PARAM,
        display_name=EDA_ANALYSIS_SPEC_PARAM,
        allow_empty_value=True,
        initial_display_value="",
    ),
]


def _eda_response() -> WDKSearchResponse:
    return WDKSearchResponse(
        search_data=WDKSearch(
            url_segment=_MUTAGENESIS_SEARCH,
            display_name=_MUTAGENESIS_SEARCH,
            query_name=SUBSET_QUERY,
            param_names=[p.name for p in _EDA_PARAMS],
            parameters=_EDA_PARAMS,
        ),
        validation=StepValidation.model_validate(
            {"level": "DISPLAYABLE", "isValid": True, "errors": None}
        ),
    )


async def _eda_details(
    ctx: SearchContext, **_kw: object
) -> tuple[WDKSearchResponse, str]:
    return _eda_response(), ctx.record_type


async def _eda_resolved(_ctx: SearchContext, **_kw: object) -> ResolvedSearch:
    return ResolvedSearch(response=_eda_response(), values_were_read=True)


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


class TestAnEdaBackedSearchIsNeverBound:
    @pytest.fixture(autouse=True)
    def _serve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        infos = format_param_info_typed(_EDA_PARAMS)
        serve_params(monkeypatch, lambda _context: infos)
        serve_definition(
            monkeypatch,
            _EDA_PARAMS,
            param_names=[p.name for p in _EDA_PARAMS],
            query_name=SUBSET_QUERY,
        )
        serve_resolution(
            monkeypatch,
            {
                EDA_DATASET_ID_PARAM: StringValue(value=_DATASET_ID),
                EDA_ANALYSIS_SPEC_PARAM: StringValue(value=_INVENTED_SPEC),
            },
        )
        monkeypatch.setattr(frame_spec, "fetch_search_details", _eda_details)
        monkeypatch.setattr(frame_spec, "make_validation_callbacks", _eda_callbacks)
        serve_search_details(monkeypatch, _eda_resolved)

    async def _sheet(
        self, state: AgentToolState, text: str = "essential in blood stages"
    ) -> SetCriterionResult:
        return returned(
            await set_criterion(
                frame_ctx(state),
                criterion_id="c_essential",
                text=text,
                search_name=_MUTAGENESIS_SEARCH,
            ),
            SetCriterionResult,
        )

    async def _bind(self, state: AgentToolState) -> SetCriterionResult:
        return await bind(
            state,
            _MUTAGENESIS_SEARCH,
            {
                EDA_DATASET_ID_PARAM: _DATASET_ID,
                EDA_ANALYSIS_SPEC_PARAM: _INVENTED_SPEC,
            },
            criterion_id="c_essential",
            text="essential in blood stages",
        )

    async def test_the_sheet_call_is_refused_and_pins_nothing(self) -> None:
        state = AgentToolState()

        with pytest.raises(ModelRetry) as excinfo:
            await self._sheet(state)

        message = str(excinfo.value)
        assert _MUTAGENESIS_SEARCH in message
        assert EDA_ANALYSIS_SPEC_PARAM in message
        assert "recorded as dropped for the Lead" in message
        assert "Do not call drop_criterion" in message
        assert state.open_sheets == {}

    async def test_the_refusal_names_the_dataset_the_search_carries(self) -> None:
        with pytest.raises(ModelRetry) as excinfo:
            await self._sheet(AgentToolState())

        assert f"dataset {_DATASET_ID}" in str(excinfo.value)

    async def test_the_refusal_names_the_eda_tools_that_build_the_step(self) -> None:
        state = AgentToolState()

        with pytest.raises(ModelRetry):
            await self._sheet(state)

        reason = state.operational_spec_draft.dropped[0].reason
        assert "open_eda_analysis" in reason
        assert "set_eda_filters" in reason
        assert "preview_eda_subset" in reason
        assert "create_eda_step" in reason

    async def test_the_refusal_records_the_drop_with_its_dataset(self) -> None:
        state = AgentToolState()

        with pytest.raises(ModelRetry):
            await self._sheet(state)

        dropped = state.operational_spec_draft.dropped
        assert len(dropped) == 1
        assert dropped[0].text == "essential in blood stages"
        assert dropped[0].eda_dataset_id == _DATASET_ID

    async def test_a_reworded_retry_on_the_same_id_records_one_drop(self) -> None:
        """The drop answers the criterion, not the words FRAME chose for it."""
        state = AgentToolState()

        for text in ("essential in blood stages", "essential in blood stages (MIS)"):
            with pytest.raises(ModelRetry):
                await self._sheet(state, text=text)

        assert [d.text for d in state.operational_spec_draft.dropped] == [
            "essential in blood stages"
        ]

    async def test_a_draft_that_already_carries_the_drop_records_no_second(
        self,
    ) -> None:
        """A later framing pass starts from a draft that carries the drop."""
        state = AgentToolState()
        state.operational_spec_draft.dropped.append(
            DroppedCriterion(
                text="essential in blood stages",
                reason=EDA_DROP_REASON,
                eda_dataset_id=_DATASET_ID,
            ),
        )

        with pytest.raises(ModelRetry):
            await self._sheet(state)

        assert len(state.operational_spec_draft.dropped) == 1

    async def test_a_later_pass_that_rewords_the_criterion_records_no_second(
        self,
    ) -> None:
        """One dataset is one analysis and one export, whatever it is called."""
        state = AgentToolState()
        state.operational_spec_draft.dropped.append(
            DroppedCriterion(
                text="essential in blood stages",
                reason=EDA_DROP_REASON,
                eda_dataset_id=_DATASET_ID,
            ),
        )

        with pytest.raises(ModelRetry):
            await self._sheet(state, text="essential in blood stages (piggyBac MIS)")

        assert [d.text for d in state.operational_spec_draft.dropped] == [
            "essential in blood stages"
        ]

    async def test_a_proposed_spec_is_refused_and_binds_nothing(self) -> None:
        state = AgentToolState()

        with pytest.raises(ModelRetry) as excinfo:
            await self._bind(state)

        assert "recorded as dropped for the Lead" in str(excinfo.value)
        assert state.operational_spec_draft.criteria == []
        assert len(state.operational_spec_draft.dropped) == 1


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


class TestADropThatNamesNoDataset:
    """A search whose definition carries no dataset default still drops."""

    def _dropped(self, text: str) -> DroppedCriterion:
        return DroppedCriterion(text=text, reason=EDA_DROP_REASON)

    def test_two_criteria_with_no_dataset_are_both_recorded(self) -> None:
        state = AgentToolState()

        state.frame_record_drop("c_one", self._dropped("blood-stage essentiality"))
        state.frame_record_drop("c_two", self._dropped("host response signature"))

        assert [d.text for d in state.operational_spec_draft.dropped] == [
            "blood-stage essentiality",
            "host response signature",
        ]

    def test_a_drop_with_no_dataset_after_an_ordinary_one_is_recorded(self) -> None:
        state = AgentToolState()
        state.frame_set_criterion(
            Criterion(id="c_gone", text="no such search", search_name="")
        )
        state.frame_drop_criterion("c_gone", "the search is unavailable")

        state.frame_record_drop("c_eda", self._dropped("blood-stage essentiality"))

        assert [d.text for d in state.operational_spec_draft.dropped] == [
            "no such search",
            "blood-stage essentiality",
        ]

    def test_two_refusals_on_one_dataset_still_record_once(self) -> None:
        state = AgentToolState()
        labelled = DroppedCriterion(
            text="essential in blood stages",
            reason=EDA_DROP_REASON,
            eda_dataset_id=_DATASET_ID,
        )

        state.frame_record_drop("c_one", labelled)
        state.frame_record_drop(
            "c_two",
            DroppedCriterion(
                text="essential in blood stages (piggyBac MIS)",
                reason=EDA_DROP_REASON,
                eda_dataset_id=_DATASET_ID,
            ),
        )

        assert state.operational_spec_draft.dropped == [labelled]
