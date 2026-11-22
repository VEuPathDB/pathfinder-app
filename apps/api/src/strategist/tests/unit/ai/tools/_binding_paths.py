from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

import pytest
from pydantic import JsonValue
from pydantic_ai import ModelRetry
from veupathdb.domain.parameters import (
    FilterFacets,
    FilterProposals,
    HeldValue,
    MultiPickValue,
    ParamValue,
    shown_stated,
)
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.wdk import WDKParameter
from veupathdb_mcp.catalog import (
    BoundValues,
    MovedParentError,
    ParameterInfo,
    ParamFetcher,
    ResolveContext,
    read_under_parents,
)

from strategist.ai.agents.state import AgentToolState
from strategist.ai.tools.standalone import (
    _frame_proposals,
    _stated_values,
    catalog_discovery,
    frame_spec,
    strategy_edits,
)
from strategist.ai.tools.standalone._stated_values import (
    StatedStepNode,
    StatedUpdateStepParamsOp,
    typed_operations,
    typed_tree,
    typed_values,
)
from strategist.ai.tools.standalone._variant_targets import resolved_variants
from strategist.ai.tools.standalone.strategy_edits import update_leaf_params
from strategist.domain.strategy.operational_spec import Criterion
from strategist.domain.strategy.operations import GraphOperation
from strategist.domain.strategy.session import StrategyGraph, StrategySession
from strategist.services.experiment import variant_comparison
from strategist.services.experiment.variant_comparison import VariantInput
from strategist.services.strategies.commit import CommitResult
from strategist.tests._support.bound_values import bound
from strategist.tests._support.filter_reads import NoFilterReads
from strategist.tests._support.param_infos import sheet_of
from strategist.tests._support.record_classes import (
    list_every_search_under,
    list_searches_under,
    serve_record_classes,
)
from strategist.tests._support.recorded_counts import no_measurements
from strategist.tests._support.recorded_searches import (
    client_search,
    no_count,
    serve_recorded,
)
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.tools._apply_operations_stubs import (
    context_and_commit,
    graph_with,
)
from strategist.tests.unit.ai.tools.conftest import (
    agent_run_context,
    serve_no_other_sites,
)
from strategist.tests.unit.ai.tools.test_frame_spec import (
    bind,
    no_validation,
    serve_site_listing,
)

PF = "Plasmodium falciparum 3D7"
VIVAX = "Plasmodium vivax P01"
SEARCH = "GenesByNgsSnps"
ORGANISM = "organismSinglePick"
SAMPLES = "variation_sample_meta"
_UNDER = {
    f'["{PF}"]': client_search("search_genes_by_ngs_snps"),
    f'["{VIVAX}"]': client_search("search_genes_by_ngs_snps_under_another_organism"),
}
_ABOUT = ResolveContext(site_id="plasmodb")


def declared(context: Mapping[str, str]) -> list[WDKParameter]:
    organism = context.get(ORGANISM, f'["{VIVAX}"]')
    return list(_UNDER[organism].parameters or [])


async def _fetch_at(context: dict[str, str]) -> list[WDKParameter]:
    return declared(context)


def fetcher(_site: str, _record_type: str, _search: str) -> ParamFetcher:
    return _fetch_at


def _peru() -> ParamValue:
    [samples] = [p for p in declared({}) if p.name == SAMPLES]
    return FilterFacets.of(samples).bind(
        FilterProposals.model_validate(
            [{"field": "Dataset", "value": ["WGS of Patient Isolates from Peru"]}]
        )
    )


HELD_CHILDREN: dict[str, ParamValue] = {
    "readable": _peru(),
    "kept": HeldValue(wire='{"filters":[{"field":"unknown"}]}'),
}
_NO_SUCH: JsonValue = [{"field": "Dataset", "value": ["No such dataset"]}]

Case = Literal["given_back", "left_out", "stated_anew", "other_case", "other_writing"]


def _stated(case: Case, child: ParamValue) -> dict[str, JsonValue]:
    match case:
        case "given_back":
            return {ORGANISM: [PF], SAMPLES: shown_stated(child)}
        case "left_out":
            return {ORGANISM: [PF]}
        case "stated_anew":
            return {ORGANISM: [PF], SAMPLES: _NO_SUCH}
        case "other_case":
            return {ORGANISM: [VIVAX.lower()]}
        case "other_writing":
            return {ORGANISM: [VIVAX]}


def _held(case: Case, child: ParamValue) -> dict[str, ParamValue]:
    organism: ParamValue = (
        HeldValue(wire=f'[ "{VIVAX}" ]')
        if case == "other_writing"
        else MultiPickValue(values=[VIVAX])
    )
    return {ORGANISM: organism, SAMPLES: child}


@dataclass(frozen=True)
class Outcome:
    kind: Literal["moved", "refused", "accepted"]
    text: str = ""
    child: ParamValue | None = None


def refused_outcome(text: str) -> Outcome:
    moved = "was read again under it and refused" in text
    return Outcome("moved" if moved else "refused", text)


def _serve_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _read(
        _site: str,
        _search: str,
        stated: Mapping[str, JsonValue] | None,
        *,
        about: ResolveContext | None,
        record_type: str | None = None,
        bound: Mapping[str, ParamValue],
    ) -> BoundValues:
        del record_type
        return await read_under_parents(
            _fetch_at, stated or {}, NoFilterReads(), about=about, bound=bound
        )

    async def _context(
        _site: str,
        _search: str,
        stated: Mapping[str, JsonValue] | None,
        *,
        about: ResolveContext | None,
        record_type: str | None = None,
        bound: Mapping[str, ParamValue],
    ) -> tuple[BoundValues, list[MovedParentError]]:
        del record_type
        stale: list[MovedParentError] = []
        values = await read_under_parents(
            _fetch_at,
            stated or {},
            NoFilterReads(),
            about=about,
            bound=bound,
            stale=stale,
        )
        return values, stale

    monkeypatch.setattr(_stated_values, "read_stated_parameters", _read)
    monkeypatch.setattr(_stated_values, "read_stated_context", _context)


def _step_graph(case: Case, child: ParamValue) -> StrategyGraph:
    return graph_with(
        StrategyStepNode(id="step_s", search_name=SEARCH, parameters=_held(case, child))
    )


def _written(child: ParamValue, parameters: Mapping[str, ParamValue]) -> Outcome:
    return Outcome("accepted", child=parameters.get(SAMPLES, child))


async def edit(
    monkeypatch: pytest.MonkeyPatch, case: Case, child: ParamValue
) -> Outcome:
    stated = _stated(case, child)
    _serve_reader(monkeypatch)
    ops: list[GraphOperation] = []

    async def _commit(*, deps: object, op: GraphOperation) -> CommitResult:
        del deps
        ops.append(op)
        return CommitResult(description="applied")

    monkeypatch.setattr(strategy_edits, "apply_and_commit", _commit)
    ctx, _ = context_and_commit(_step_graph(case, child), [])
    try:
        await update_leaf_params(ctx, "step_s", stated)
    except ModelRetry as refusal:
        return refused_outcome(refusal.message)
    [op] = ops
    return _written(child, op.model_dump(mode="python")["parameters"])


async def typed_operation(
    monkeypatch: pytest.MonkeyPatch, case: Case, child: ParamValue
) -> Outcome:
    stated = _stated(case, child)
    _serve_reader(monkeypatch)
    try:
        [op] = await typed_operations(
            _ABOUT,
            _step_graph(case, child),
            [StatedUpdateStepParamsOp(step_id="step_s", parameters=stated)],
        )
    except ModelRetry as refusal:
        return refused_outcome(refusal.message)
    return _written(child, op.model_dump(mode="python")["parameters"])


def criterion_holding(case: Case, child: ParamValue) -> Criterion:
    return Criterion(
        id="c_snps",
        text="SNPs in the Peru isolates",
        search_name=SEARCH,
        record_class="transcript",
        resolved_params=bound(_held(case, child)),
    )


async def options(
    monkeypatch: pytest.MonkeyPatch, case: Case, child: ParamValue
) -> Outcome:
    stated = _stated(case, child)
    _serve_reader(monkeypatch)

    async def _read(*_args: object, **_kwargs: object) -> ParameterInfo:
        return ParameterInfo(
            name="MinPercentMinorAlleles",
            display_name="Minor alleles",
            type="string",
            required=True,
            is_visible=True,
            site_set=False,
            help="",
        )

    monkeypatch.setattr(catalog_discovery, "read_parameter_options", _read)
    ctx = agent_run_context()
    ctx.deps.agent_state.frame_set_criterion(criterion_holding(case, child))
    try:
        info = returned(
            await catalog_discovery.get_parameter_options(
                ctx, SEARCH, "MinPercentMinorAlleles", context_values=stated
            ),
            ParameterInfo,
        )
    except ModelRetry as refusal:
        return refused_outcome(refusal.message)
    if info.note:
        return refused_outcome(info.note)
    return Outcome("accepted")


async def variant(
    monkeypatch: pytest.MonkeyPatch, case: Case, child: ParamValue
) -> Outcome:
    stated = _stated(case, child)
    _serve_reader(monkeypatch)
    serve_record_classes(monkeypatch)
    list_searches_under(monkeypatch, "transcript", [SEARCH])

    async def _sheet(
        _site: str, _record_type: str, _search: str, context: dict[str, str]
    ) -> list[ParameterInfo]:
        return sheet_of(declared(context))

    monkeypatch.setattr(variant_comparison, "search_parameters", _sheet)
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph("g1", "snps", "plasmodb")
    graph.steps = flatten_tree(
        StrategyStepNode(id="step_s", search_name=SEARCH, parameters=_held(case, child))
    )
    graph.recompute_roots()
    session.graph = graph
    variant = VariantInput.model_validate(
        {"label": "falciparum", "searchName": SEARCH, "parameters": stated}
    )
    try:
        await resolved_variants(session, [variant], _ABOUT)
    except ModelRetry as refusal:
        return refused_outcome(refusal.message)
    return Outcome("accepted")


def _serve_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    list_every_search_under(monkeypatch, "transcript")
    serve_recorded(monkeypatch, [_UNDER[f'["{VIVAX}"]']])
    monkeypatch.setattr(frame_spec, "wdk_fetch_at", fetcher)
    monkeypatch.setattr(
        _frame_proposals, "WDKFilterReads", lambda *_args: NoFilterReads()
    )
    no_validation(monkeypatch)
    no_count(monkeypatch)
    no_measurements(monkeypatch)
    serve_site_listing(monkeypatch, [])
    serve_no_other_sites(monkeypatch)


async def frame(
    monkeypatch: pytest.MonkeyPatch, case: Case, child: ParamValue
) -> Outcome:
    stated = _stated(case, child)
    _serve_frame(monkeypatch)
    state = AgentToolState()
    first: dict[str, JsonValue] = {
        info.name: None for info in sheet_of(declared({})) if info.bindable
    }
    await bind(
        state,
        SEARCH,
        {**first, ORGANISM: [VIVAX], SAMPLES: shown_stated(_peru())},
        criterion_id="c_snps",
        text="SNPs in the Peru isolates",
    )
    [held] = state.operational_spec_draft.criteria
    samples = held.resolved_params[SAMPLES].model_copy(update={"value": child})
    state.operational_spec_draft = state.operational_spec_draft.model_copy(
        update={
            "criteria": [
                held.model_copy(
                    update={
                        "resolved_params": {**held.resolved_params, SAMPLES: samples}
                    }
                )
            ]
        }
    )
    try:
        await bind(
            state,
            SEARCH,
            stated,
            criterion_id="c_snps",
            text="SNPs in the Peru isolates",
        )
    except ModelRetry as refusal:
        return refused_outcome(refusal.message)
    [rebound] = state.operational_spec_draft.criteria
    return Outcome("accepted", child=rebound.resolved_params[SAMPLES].value)


def _built(parameters: Mapping[str, ParamValue]) -> Outcome:
    return Outcome("accepted", child=parameters.get(SAMPLES))


async def build(
    monkeypatch: pytest.MonkeyPatch, case: Case, child: ParamValue
) -> Outcome:
    stated = _stated(case, child)
    _serve_reader(monkeypatch)
    try:
        tree = await typed_tree(
            _ABOUT, StatedStepNode(search_name=SEARCH, parameters=stated)
        )
    except ModelRetry as refusal:
        return refused_outcome(refusal.message)
    return _built(tree.parameters)


async def control_test(
    monkeypatch: pytest.MonkeyPatch, case: Case, child: ParamValue
) -> Outcome:
    stated = _stated(case, child)
    _serve_reader(monkeypatch)
    try:
        values = await typed_values(_ABOUT, SEARCH, stated)
    except ModelRetry as refusal:
        return refused_outcome(refusal.message)
    return _built(values)
