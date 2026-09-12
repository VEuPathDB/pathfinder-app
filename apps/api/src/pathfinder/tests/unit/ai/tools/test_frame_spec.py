"""``set_criterion``: the parameter sheet, the search registry, the record.

The scaffolding at the top is shared with the other frame test modules.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from unittest.mock import MagicMock

import pytest
from pydantic_ai import ModelRetry, RunContext
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    StringValue,
    VocabOption,
)
from veupathdb.domain.strategy import StepValidation
from veupathdb.errors import ValidationError
from veupathdb.wdk import WDKParameter, WDKSearch, WDKSearchResponse, WDKStringParam
from veupathdb_mcp.catalog import (
    COMPUTE_QUERY,
    EDA_ANALYSIS_SPEC_PARAM,
    EDA_DATASET_ID_PARAM,
    ParameterInfo,
    ParamFetcher,
    ResolvedParams,
    ResolvedSearch,
    ValidatedParams,
    ValidationCallbacks,
    format_param_info_typed,
    search_inspection,
    searches,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import frame_spec
from pathfinder.ai.tools.standalone._frame_proposals import DeclaredAssumption
from pathfinder.ai.tools.standalone.frame_spec import (
    SetCriterionResult,
    drop_criterion,
    set_criterion,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.tests._support.catalog_builders import ParamsAt, serve_search_details
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

Proposals = dict[str, str | list[str] | None]


def _transcript_session() -> StrategySession:
    """A session holding one transcript graph, which every criterion binds on."""
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="g", site_id="plasmodb")
    graph.record_type = "transcript"
    session.add_graph(graph)
    return session


def frame_ctx(state: AgentToolState) -> RunContext[AgentDeps]:
    return agent_run_context(agent_state=state, strategy_session=_transcript_session())


def param_info(
    name: str, param_type: str = "string", **fields: object
) -> ParameterInfo:
    defaults: dict[str, object] = {
        "name": name,
        "display_name": name,
        "type": param_type,
        "required": True,
        "is_visible": True,
        "help": "",
        "value_format": "",
    }
    return ParameterInfo.model_validate(defaults | fields)


def serve_params(monkeypatch: pytest.MonkeyPatch, at: ParamsAt) -> None:
    def _fetch_at(*_args: object) -> ParamFetcher:
        async def fetch_at(context: dict[str, str]) -> list[ParameterInfo]:
            return at(context)

        return fetch_at

    monkeypatch.setattr(frame_spec, "wdk_fetch_at", _fetch_at)


def serve_definition(
    monkeypatch: pytest.MonkeyPatch,
    parameters: list[WDKParameter] | None = None,
    **fields: object,
) -> list[str]:
    reads: list[str] = []

    async def _details(
        record_type: str, name: str, *, expand_params: bool = True
    ) -> WDKSearchResponse:
        del record_type, expand_params
        reads.append(name)
        return WDKSearchResponse(
            search_data=WDKSearch.model_validate(
                {"url_segment": name, "parameters": parameters or [], **fields}
            ),
            validation=StepValidation(level="NONE", is_valid=False),
        )

    client = MagicMock()
    client.get_search_details = _details
    client.get_search_details_with_params = _details
    monkeypatch.setattr(searches, "get_wdk_client", lambda _site: client)
    monkeypatch.setattr(search_inspection, "get_wdk_client", lambda _site: client)
    return reads


def serve_catalog(
    monkeypatch: pytest.MonkeyPatch,
    parameters: list[WDKParameter],
    properties: dict[str, list[str]] | None = None,
    **fields: str,
) -> list[SearchContext]:
    seen: list[SearchContext] = []

    async def _details(
        ctx: SearchContext, **_kw: object
    ) -> tuple[WDKSearchResponse, str]:
        seen.append(ctx)
        return (
            WDKSearchResponse(
                search_data=WDKSearch.model_validate(
                    {
                        "url_segment": ctx.search_name,
                        "parameters": parameters,
                        "properties": properties or {},
                        **fields,
                    }
                ),
                validation=StepValidation(level="NONE", is_valid=False),
            ),
            ctx.record_type,
        )

    monkeypatch.setattr(frame_spec, "fetch_search_details", _details)
    return seen


def no_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _validate(*_args: object, **_kwargs: object) -> ValidatedParams:
        return ValidatedParams()

    monkeypatch.setattr(frame_spec, "validate_parameters", _validate)


def serve_search(
    monkeypatch: pytest.MonkeyPatch,
    at: ParamsAt,
    *,
    catalog: list[WDKParameter] | None = None,
    properties: dict[str, list[str]] | None = None,
    **fields: str,
) -> list[SearchContext]:
    serve_params(monkeypatch, at)
    serve_definition(monkeypatch)
    no_validation(monkeypatch)
    return serve_catalog(monkeypatch, catalog or [], properties, **fields)


async def bind(
    state: AgentToolState,
    search_name: str,
    params: Proposals | None = None,
    *,
    criterion_id: str = "c1",
    text: str = "kinases",
    assumed: list[DeclaredAssumption] | None = None,
) -> SetCriterionResult:
    return returned(
        await set_criterion(
            frame_ctx(state),
            criterion_id=criterion_id,
            text=text,
            search_name=search_name,
            params=params,
            assumed=assumed,
        ),
        SetCriterionResult,
    )


_ORGANISMS = [
    VocabOption(value="Plasmodium", display="Plasmodium"),
    VocabOption(value="Plasmodium falciparum 3D7", display="P. falciparum 3D7"),
]
_TEXT_FIELDS = [
    VocabOption(value="product", display="product"),
    VocabOption(value="Notes", display="Notes"),
]

KINASE_PARAMS: Proposals = {
    "text_expression": "kinase",
    "text_search_organism": ["Plasmodium"],
    "document_type": None,
    "text_fields": None,
}


def genes_by_text(_context: dict[str, str]) -> list[ParameterInfo]:
    return [
        param_info("text_expression"),
        param_info(
            "text_search_organism", "multi-pick-vocabulary", vocab_leaves=_ORGANISMS
        ),
        param_info("document_type", required=False, default_value="gene"),
        param_info(
            "text_fields",
            "multi-pick-vocabulary",
            required=False,
            vocab_leaves=_TEXT_FIELDS,
            default_value='["product", "Notes"]',
        ),
    ]


def test_drop_criterion_removes_from_criteria_and_records() -> None:
    st = AgentToolState()
    st.frame_set_criterion(
        Criterion(id="c_x", text="disorder fraction", search_name="S1")
    )
    st.frame_set_criterion(Criterion(id="c_keep", text="keep me", search_name="S2"))

    drop_criterion(frame_ctx(st), criterion_id="c_x", reason="search down")

    assert [c.id for c in st.operational_spec_draft.criteria] == ["c_keep"]
    dropped = st.operational_spec_draft.dropped[0]
    assert dropped.text == "disorder fraction"
    assert dropped.reason == "search down"


def test_drop_criterion_unblocks_ready_to_build() -> None:
    # A dropped-but-not-removed criterion with an open param keeps
    # ready_to_build False forever, so nothing recovers from a down search.
    st = AgentToolState()
    st.frame_set_criterion(Criterion(id="ok", text="bound", search_name="S1"))
    st.frame_set_criterion(
        Criterion(
            id="broken",
            text="broken",
            search_name="GenesByOrthologPattern",
            open_params=[OpenSlot(param_name="organism", question="pick")],
        )
    )
    st.operational_spec_draft.structure = SpecStructure(
        root=StructureNode(kind="leaf", criterion_id="ok")
    )
    assert st.operational_spec_draft.ready_to_build is False

    drop_criterion(frame_ctx(st), criterion_id="broken", reason="search down")

    assert st.operational_spec_draft.ready_to_build is True


def test_drop_criterion_unknown_id_raises_model_retry() -> None:
    st = AgentToolState()
    st.frame_set_criterion(Criterion(id="c1", text="a", search_name="S1"))
    with pytest.raises(ModelRetry):
        drop_criterion(frame_ctx(st), criterion_id="nope", reason="x")


def serve_resolution(
    monkeypatch: pytest.MonkeyPatch,
    params: Mapping[str, ParamValue],
    *,
    open_slots: Sequence[OpenSlot] = (),
    unresolved: Sequence[str] = (),
) -> None:
    async def _resolve(**_kw: object) -> ResolvedParams:
        return ResolvedParams(
            params=dict(params),
            open_slots=list(open_slots),
            unresolved_required=list(unresolved),
        )

    monkeypatch.setattr(frame_spec, "resolve_params_with_intent", _resolve)


@pytest.mark.asyncio
async def test_set_criterion_retries_on_invalid_resolved_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A complete binding whose resolved values WDK rejects must surface a
    # did-you-mean retry at FRAME, not slip through to fail the build.
    st = AgentToolState()
    serve_search(
        monkeypatch,
        lambda _context: [param_info("text_fields", "multi-pick-vocabulary")],
    )
    serve_resolution(
        monkeypatch, {"text_fields": MultiPickValue(values=["product,Notes"])}
    )

    async def _validate(_ctx: object, **_kw: object) -> ValidatedParams:
        raise ValidationError(
            title="Invalid parameter value: Parameter 'text_fields' does not "
            "accept 'product,Notes'."
        )

    monkeypatch.setattr(frame_spec, "validate_parameters", _validate)

    with pytest.raises(ModelRetry) as exc:
        await bind(
            st,
            "GenesByText",
            {"text_fields": "product,Notes"},
            text="annotated male gametocyte",
        )

    assert "does not accept" in str(exc.value), "the WDK rejection, not a name check"
    assert "text_fields" in str(exc.value)
    assert st.operational_spec_draft.criteria == []


@pytest.mark.asyncio
async def test_set_criterion_skips_validation_when_open_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Open slots mean a required param is unresolved; validating now would
    # falsely trip "missing required".
    st = AgentToolState()
    validated = False
    serve_search(monkeypatch, lambda _context: [])
    serve_resolution(
        monkeypatch,
        {"organism": MultiPickValue(values=["Pf3D7"])},
        open_slots=[OpenSlot(param_name="samples", question="pick")],
        unresolved=["samples"],
    )

    async def _validate(_ctx: object, **_kw: object) -> ValidatedParams:
        nonlocal validated
        validated = True
        return ValidatedParams()

    monkeypatch.setattr(frame_spec, "validate_parameters", _validate)

    result = await bind(st, "GenesByRNASeq", {}, text="x")

    assert validated is False
    assert any(s.param_name == "samples" for s in result.open_slots)
    assert st.operational_spec_draft.criteria[0].id == "c1"


@pytest.mark.asyncio
async def test_set_criterion_binds_when_resolved_params_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    st = AgentToolState()
    bound = {"organism": MultiPickValue(values=["Pf3D7"])}
    serve_search(monkeypatch, lambda _context: [])
    serve_resolution(monkeypatch, bound)

    async def _validate(_ctx: object, **_kw: object) -> ValidatedParams:
        return ValidatedParams(params=dict(bound))

    monkeypatch.setattr(frame_spec, "validate_parameters", _validate)

    result = await bind(st, "GenesWithSignalPeptide", {}, text="x")

    assert isinstance(result, SetCriterionResult)
    assert result.criterion_id == "c1"
    assert result.search_name == "GenesWithSignalPeptide"
    # Report the bound VALUE, not just the name: a silently wrong binding is
    # invisible when only names come back.
    assert result.resolved_params == {"organism": '["Pf3D7"]'}
    assert result.open_slots == []
    # A proposal already carries the names, so the template would only repeat them.
    assert result.params_template == {}
    assert st.operational_spec_draft.criteria[0].id == "c1"


_DATASET_ID = "DS_e973eadd57"
_DESEQ_SEARCH = "GenesByRNASeqpfal3D7_Pfal3D7_Febrile_temps_RNASeq_ebi_rnaSeq_RSRCDESeq"
_INVENTED_SPEC = (
    '{"data_type":"read counts",'
    '"comparison":{"case":"febrile","control":"normal"},'
    '"fold_change":{"direction":"both","minimum":2},'
    '"adjusted_p_value":{"maximum":0.05}}'
)
_EDA_PARAMS: list[WDKParameter] = [
    WDKStringParam(
        name=name, display_name=name, allow_empty_value=True, initial_display_value=""
    )
    for name in (EDA_DATASET_ID_PARAM, EDA_ANALYSIS_SPEC_PARAM)
]


def _eda_response() -> WDKSearchResponse:
    return WDKSearchResponse(
        search_data=WDKSearch(
            url_segment=_DESEQ_SEARCH,
            display_name=_DESEQ_SEARCH,
            query_name=COMPUTE_QUERY,
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


class TestAProposedEdaSpecComesBackAsARetry:
    @pytest.fixture(autouse=True)
    def _serve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        infos = format_param_info_typed(_EDA_PARAMS)
        serve_params(monkeypatch, lambda _context: infos)
        serve_definition(monkeypatch, _EDA_PARAMS)
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

    async def _call(self, state: AgentToolState) -> SetCriterionResult:
        return await bind(
            state,
            _DESEQ_SEARCH,
            {
                EDA_DATASET_ID_PARAM: _DATASET_ID,
                EDA_ANALYSIS_SPEC_PARAM: _INVENTED_SPEC,
            },
            criterion_id="c_deseq",
            text="genes up in febrile against normal",
        )

    @pytest.mark.asyncio
    async def test_the_retry_names_the_eda_tools_and_the_spec_parameter(self) -> None:
        with pytest.raises(ModelRetry) as excinfo:
            await self._call(AgentToolState())

        message = str(excinfo.value)
        assert "open_eda_analysis" in message
        assert "set_eda_filters" in message
        assert "run_eda_compute" in message
        assert "create_eda_step" in message
        assert EDA_ANALYSIS_SPEC_PARAM in message

    @pytest.mark.asyncio
    async def test_the_criterion_is_not_bound(self) -> None:
        state = AgentToolState()

        with pytest.raises(ModelRetry):
            await self._call(state)

        assert state.operational_spec_draft.criteria == []
