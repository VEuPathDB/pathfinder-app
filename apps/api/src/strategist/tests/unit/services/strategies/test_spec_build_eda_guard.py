"""A declarative build stops at validation when the EDA spec was proposed."""

from __future__ import annotations

import pytest
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import ParamValue, StringValue
from veupathdb.domain.strategy import (
    StepValidation,
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

from strategist.services.eda.authoring import new_analysis, serialize_spec
from strategist.services.strategies import commit_tree
from strategist.services.strategies.commit_tree import CommitTarget, CommittedTree
from strategist.services.strategies.sync_state import WDKSyncState
from strategist.tests._support.catalog_builders import serve_search_details
from strategist.tests._support.record_classes import list_every_search_under

from ._counting_strategy_api import CountingStrategyAPI

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


def _serve(monkeypatch: pytest.MonkeyPatch) -> CountingStrategyAPI:
    """Answer the WDK reads, and record every step write."""
    api = CountingStrategyAPI()

    async def _resolved(
        ctx: SearchContext,
        *,
        resolved_record_type: str,
        parameters: dict[str, ParamValue],
    ) -> ResolvedSearch:
        del ctx, resolved_record_type, parameters
        return ResolvedSearch(response=_response(), values_were_read=True)

    serve_search_details(monkeypatch, _resolved)
    list_every_search_under(monkeypatch, "transcript")
    monkeypatch.setattr(commit_tree, "make_validation_callbacks", _callbacks)
    monkeypatch.setattr(commit_tree, "get_strategy_api", lambda _site: api)
    return api


async def _build(spec: str) -> CommittedTree:
    root = StrategyStepNode(
        search_name=_DESEQ_SEARCH,
        parameters={
            EDA_DATASET_ID_PARAM: StringValue(value=_DATASET_ID),
            EDA_ANALYSIS_SPEC_PARAM: StringValue(value=spec),
        },
    )
    return await commit_tree.commit_tree(
        site_id="plasmodb",
        steps=flatten_tree(root),
        root_id=root.id,
        old=None,
        sync_state=WDKSyncState(),
        target=CommitTarget(name="DESeq", description=""),
    )


class TestTheInventedSpecNeverReachesCreateStep:
    @pytest.mark.asyncio
    async def test_no_step_is_pushed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = _serve(monkeypatch)

        await _build(_INVENTED_SPEC)

        assert api.calls == []

    @pytest.mark.asyncio
    async def test_the_node_fails_with_the_eda_guidance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _serve(monkeypatch)

        committed = await _build(_INVENTED_SPEC)

        (refusal,) = committed.drafts.values()
        assert committed.failures == []
        assert "an analysis is opened on it" in refusal
        assert "The step is built from the open analysis." in refusal

    @pytest.mark.asyncio
    async def test_an_authored_spec_still_pushes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _serve(monkeypatch)

        committed = await _build(_authored_spec())

        assert (committed.failures, committed.drafts) == ([], {})
        assert [c.kwargs["search_name"] for c in api.named("create_step")] == [
            _DESEQ_SEARCH
        ]
