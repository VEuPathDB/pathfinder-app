from __future__ import annotations

import pytest
from pydantic import JsonValue, TypeAdapter
from veupathdb.domain.parameters import (
    KEPT_MARK,
    FilterValue,
    HeldValue,
    MultiPickValue,
    ParamValue,
    from_wire,
    shown_stated,
)
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.wdk import WDKAnswer, WDKParameter
from veupathdb_mcp.catalog import ResolveContext, read_under_parents

from strategist.ai.lead.edit_messages import EditMessage, edit_work_order
from strategist.ai.lead.live_state import read_live_state
from strategist.ai.tools.standalone._frame_proposals import CriterionCall
from strategist.ai.tools.standalone._stated_values import (
    StatedUpdateStepParamsOp,
    typed_operations,
)
from strategist.ai.tools.standalone.strategy_graph import (
    StrategySummaryResponse,
    get_strategy,
)
from strategist.domain.strategy.operational_spec import Criterion, OperationalSpec
from strategist.domain.strategy.operations import UpdateStepParamsOp
from strategist.domain.strategy.spec_diff import SpecDiff
from strategist.services.experiment import search_reads
from strategist.services.experiment.variant_comparison import VariantSpec
from strategist.tests._support.bound_values import bound
from strategist.tests._support.filter_reads import NoFilterReads
from strategist.tests._support.recorded_searches import (
    serve_stated_reads,
    suite_search,
)
from strategist.tests._support.tool_returns import returned
from strategist.tests.unit.ai.tools._apply_operations_stubs import (
    context_and_commit,
    graph_with,
)

_PF = "Plasmodium falciparum 3D7"
_P01 = "Plasmodium vivax P01"
_VARIANTS = suite_search("search_genes_by_variant_characteristics")
_SIGNAL = suite_search("search_genes_with_signal_peptide")
_AT_LEAST_ONE = from_wire(
    "filter",
    '{"filters": [{"field": "total_variants", "type": "number", "isRange": true, '
    '"includeUnknown": false, "value": {"min": 1.0}}]}',
)
_KEPT = HeldValue(wire="x,y")
_STATED: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])
_PLASMO = ResolveContext(site_id="plasmodb")


def _snps_spec() -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(
                id="c_snps",
                text="SNPs in vivax",
                search_name="GenesByNgsSnps",
                resolved_params=bound(
                    {
                        "organismSinglePick": MultiPickValue(values=[_P01]),
                        "variation_sample_meta": FilterValue(),
                        "MinPercentMinorAlleles": _KEPT,
                    }
                ),
            )
        ]
    )


def test_a_work_order_shows_a_kept_value_marked_and_a_pick_as_its_list() -> None:
    spec = _snps_spec()

    order = edit_work_order(
        "the researcher moves the organism",
        EditMessage(prompt="use vivax"),
        spec,
        pending=SpecDiff(),
        answered=spec,
    )

    assert "    variation_sample_meta=[]" in order
    assert f"    MinPercentMinorAlleles='x,y' {KEPT_MARK}" in order
    assert f'    organismSinglePick=["{_P01}"]' in order
    assert "leave its name out of `params` and it stays as it is" in order


def _variant_step() -> dict[str, ParamValue]:
    return {
        "gene_variant_stats": _AT_LEAST_ONE,
        "organism_select_none": MultiPickValue(values=[_PF]),
    }


async def test_get_strategy_shows_values_an_edit_reads_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_stated_reads(monkeypatch, [_VARIANTS])
    graph = graph_with(
        StrategyStepNode(
            id="step_v",
            search_name="GenesByVariantCharacteristics",
            parameters=_variant_step(),
        )
    )
    ctx, _ = context_and_commit(graph, [])

    result = await get_strategy(ctx, summary_only=False)
    shown = _STATED.validate_python(
        returned(result, StrategySummaryResponse).model_dump(
            by_alias=True, mode="json"
        )["steps"][0]["parameters"]
    )
    [read] = await typed_operations(
        _PLASMO, graph, [StatedUpdateStepParamsOp(step_id="step_v", parameters=shown)]
    )

    assert shown == {
        "gene_variant_stats": [{"field": "total_variants", "value": {"min": 1.0}}],
        "organism_select_none": [_PF],
    }
    assert read == UpdateStepParamsOp(step_id="step_v", parameters=_variant_step())


async def test_the_live_state_and_a_search_count_show_the_organism_as_stated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_stated_reads(monkeypatch, [_SIGNAL])
    organism = MultiPickValue(values=[_PF])
    graph = graph_with(
        StrategyStepNode(
            id="step_s",
            search_name="GenesWithSignalPeptide",
            parameters={"organism": organism},
        )
    )
    ctx, _ = context_and_commit(graph, [])

    async def _answer(*_args: object, **_kwargs: object) -> WDKAnswer:
        return WDKAnswer.model_validate(
            {"meta": {"displayViewTotalCount": 12, "attributes": []}, "records": []}
        )

    monkeypatch.setattr(search_reads, "run_variant_search", _answer)
    live = await read_live_state(ctx.deps.strategy_session, "plasmodb")
    shown = live.model_dump(mode="json")["steps"][0]["parameters"]
    counted = await search_reads.search_count(
        "plasmodb",
        VariantSpec(
            label="signal",
            search_name="GenesWithSignalPeptide",
            record_type="transcript",
            parameters={"organism": organism},
        ),
    )
    [read] = await typed_operations(
        _PLASMO,
        graph,
        [StatedUpdateStepParamsOp(step_id="step_s", parameters=shown)],
    )

    assert shown == {"organism": [_PF]}
    assert counted.values == {"organism": [_PF]}
    assert read == UpdateStepParamsOp(
        step_id="step_s", parameters={"organism": organism}
    )


async def test_a_call_holding_a_clause_reads_its_own_values_back() -> None:
    call = CriterionCall(
        criterion_id="c_variants",
        search_name="GenesByVariantCharacteristics",
        text="genes with a variant",
        params={},
    ).with_values(_variant_step())

    async def fetch_at(_context: dict[str, str]) -> list[WDKParameter]:
        return list(_VARIANTS.parameters or [])

    read = await read_under_parents(
        fetch_at, call.params, NoFilterReads(), about=_PLASMO
    )

    assert read == _variant_step()


def test_a_call_keeps_a_kept_value_out_of_what_it_states() -> None:
    call = CriterionCall(
        criterion_id="c_snps", search_name="GenesByNgsSnps", text="SNPs", params={}
    ).with_values({"variation_sample_meta": _KEPT})

    assert call.params == {}
    assert call.values == {"variation_sample_meta": _KEPT}


async def test_an_edit_that_gives_a_kept_value_back_keeps_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_stated_reads(monkeypatch, [_VARIANTS])
    held = HeldValue(wire='{"filters":[{"field":"unknown"}]}')
    graph = graph_with(
        StrategyStepNode(
            id="step_v",
            search_name="GenesByVariantCharacteristics",
            parameters={**_variant_step(), "gene_variant_stats": held},
        )
    )

    [read] = await typed_operations(
        _PLASMO,
        graph,
        [
            StatedUpdateStepParamsOp(
                step_id="step_v",
                parameters={
                    "gene_variant_stats": shown_stated(held),
                    "organism_select_none": [_PF],
                },
            )
        ],
    )

    assert read == UpdateStepParamsOp(
        step_id="step_v",
        parameters={
            "gene_variant_stats": held,
            "organism_select_none": MultiPickValue(values=[_PF]),
        },
    )
