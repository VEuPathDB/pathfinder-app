"""A declarative build stops at validation when the EDA spec was proposed."""

from __future__ import annotations

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import (
    StepValidation,
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
)
from veupathdb.eda import EdaStringSetFilter
from veupathdb.wdk import (
    WDKParameter,
    WDKSearch,
    WDKSearchResponse,
    WDKStringParam,
)
from veupathdb_mcp.catalog import (
    COMPUTE_QUERY,
    EDA_ANALYSIS_SPEC_PARAM,
    EDA_DATASET_ID_PARAM,
    ResolvedSearch,
    ValidationCallbacks,
)

from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.services.eda.authoring import new_analysis, serialize_spec
from pathfinder.services.strategies import spec_build
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.catalog_builders import serve_search_details

_DATASET_ID = "DS_e973eadd57"
_DESEQ_SEARCH = "GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq"
_INVENTED_SPEC = (
    '{"data_type":"read counts",'
    '"comparison":{"case":"febrile","control":"normal"},'
    '"fold_change":{"direction":"both","minimum":2},'
    '"adjusted_p_value":{"maximum":0.05}}'
)


def _authored_spec() -> str:
    return serialize_spec(
        new_analysis(
            dataset_id=_DATASET_ID,
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


def _parameters() -> list[WDKParameter]:
    return [
        WDKStringParam(
            name=EDA_DATASET_ID_PARAM,
            display_name=EDA_DATASET_ID_PARAM,
            allow_empty_value=True,
            initial_display_value="",
        ),
        WDKStringParam(
            name=EDA_ANALYSIS_SPEC_PARAM,
            display_name=EDA_ANALYSIS_SPEC_PARAM,
            allow_empty_value=True,
            initial_display_value="",
        ),
    ]


def _response() -> WDKSearchResponse:
    parameters = _parameters()
    return WDKSearchResponse(
        search_data=WDKSearch(
            url_segment=_DESEQ_SEARCH,
            display_name=_DESEQ_SEARCH,
            query_name=COMPUTE_QUERY,
            param_names=[p.name for p in parameters],
            parameters=parameters,
        ),
        validation=StepValidation.model_validate(
            {"level": "DISPLAYABLE", "isValid": True, "errors": None}
        ),
    )


def _callbacks(site_id: str, **_kw: object) -> ValidationCallbacks:
    del site_id

    async def _record_type(
        record_type: str | None,
        search_name: str | None,
    ) -> str | None:
        del search_name
        return record_type

    async def _hint(search_name: str, record_type: str | None) -> str | None:
        del search_name, record_type
        return None

    return ValidationCallbacks(
        resolve_record_type_for_search=_record_type, find_record_type_hint=_hint
    )


def _serve(monkeypatch: pytest.MonkeyPatch) -> list[StrategyStep]:
    """Answer the WDK reads, and record every step that reaches the push."""
    pushed: list[StrategyStep] = []

    async def _resolved(
        ctx: SearchContext,
        *,
        resolved_record_type: str,
        parameters: dict[str, ParamValue],
    ) -> ResolvedSearch:
        del ctx, resolved_record_type, parameters
        return ResolvedSearch(response=_response(), values_were_read=True)

    async def _push(
        *,
        sync_state: WDKSyncState,
        step: StrategyStep,
        site_id: str,
        record_type: str,
        search_name: str,
        parameters: dict[str, ParamValue],
    ) -> tuple[int | None, StepValidation | None, str | None]:
        del sync_state, site_id, record_type, search_name, parameters
        pushed.append(step)
        return 440185943, None, None

    serve_search_details(monkeypatch, _resolved)
    monkeypatch.setattr(spec_build, "make_validation_callbacks", _callbacks)
    monkeypatch.setattr(spec_build, "push_step_to_wdk", _push)
    return pushed


async def _build(spec: str) -> tuple[BuildOutcome, WDKSyncState]:
    root = StrategyStepNode(
        search_name=_DESEQ_SEARCH,
        parameters={
            EDA_DATASET_ID_PARAM: StringValue(value=_DATASET_ID),
            EDA_ANALYSIS_SPEC_PARAM: StringValue(value=spec),
        },
    )
    steps = flatten_tree(root)
    outcome = BuildOutcome()
    sync_state = WDKSyncState()
    await spec_build._push_tree_to_wdk(
        nodes=[steps[root.id]],
        graph_record_type="transcript",
        site_id="plasmodb",
        sync_state=sync_state,
        outcome=outcome,
    )
    return outcome, sync_state


class TestTheInventedSpecNeverReachesCreateStep:
    @pytest.mark.asyncio
    async def test_no_step_is_pushed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        pushed = _serve(monkeypatch)

        await _build(_INVENTED_SPEC)

        assert pushed == []

    @pytest.mark.asyncio
    async def test_the_node_fails_with_the_eda_guidance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(monkeypatch)

        outcome, _sync = await _build(_INVENTED_SPEC)

        assert len(outcome.failed_steps) == 1
        failure = outcome.failed_steps[0]
        assert failure.search_name == _DESEQ_SEARCH
        assert "open_eda_analysis" in failure.error
        assert "create_eda_step" in failure.error

    @pytest.mark.asyncio
    async def test_an_authored_spec_still_pushes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pushed = _serve(monkeypatch)

        outcome, _sync = await _build(_authored_spec())

        assert outcome.failed_steps == []
        assert [step.search_name for step in pushed] == [_DESEQ_SEARCH]
