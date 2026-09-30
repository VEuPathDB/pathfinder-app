"""A comparison of a search the strategy combines counts the result with each
variant in place (227 genes at a minimum of 2 TM domains, 82 at 3), and a
parameter the search does not take is refused with the ones it takes."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import StringValue, to_wire
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode, walk
from veupathdb.wdk import WDKAnswer, WDKSearchConfig
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.tools.standalone.variant_comparison import compare_search_variants
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.experiment import variant_comparison
from pathfinder.services.experiment.variant_comparison import (
    VariantComparison,
    VariantSpec,
)
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.tools._strategy_edit_stubs import combine, session_with
from pathfinder.tests.unit.ai.tools.test_frame_spec import param_info

_TM = "GenesByTransmembraneDomains"
_LEAF_COUNTS = {"2": 1490, "3": 1029}
_RESULT_COUNTS = {"2": 227, "3": 82}


def _strategy() -> StrategyStepNode:
    return combine(
        "step_intersect",
        StrategyStepNode(
            id="step_sp",
            search_name="GenesWithSignalPeptide",
            display_name="Predicted Signal Peptide",
        ),
        StrategyStepNode(
            id="step_tm",
            search_name=_TM,
            display_name="Transmembrane Domain Count",
            parameters={
                "min_tm": StringValue(value="2"),
                "max_tm": StringValue(value="99"),
            },
        ),
    )


def _variant(label: str, **values: str) -> VariantSpec:
    return VariantSpec.model_validate(
        {
            "label": label,
            "searchName": _TM,
            "parameters": {
                name: {"type": "string", "value": value}
                for name, value in values.items()
            },
        }
    )


class _Reports:
    async def run_search_report(
        self,
        record_type: str,
        search_name: str,
        search_config: WDKSearchConfig,
        *,
        report_config: object,
        view_filters: object,
    ) -> WDKAnswer:
        del record_type, search_name, report_config, view_filters
        total = _LEAF_COUNTS[search_config.parameters["min_tm"]]
        return WDKAnswer.model_validate(
            {"meta": {"totalCount": total, "displayTotalCount": total}, "records": []}
        )


async def _counted(payload: StrategyAst, site_id: str) -> Mapping[str, int | None]:
    del site_id
    tm = next(node for node in walk(payload.root) if node.id == "step_tm")
    return {payload.root.id: _RESULT_COUNTS[to_wire(tm.parameters["min_tm"])]}


async def _takes(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id, record_type, context
    assert search_name == _TM
    return [param_info(name) for name in ("organism", "min_tm", "max_tm")]


@pytest.fixture(autouse=True)
def _site(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(variant_comparison, "get_wdk_client", lambda _site: _Reports())
    monkeypatch.setattr(variant_comparison, "compute_plan_step_counts", _counted)
    monkeypatch.setattr(variant_comparison, "search_parameters", _takes)


async def test_each_variant_is_counted_at_the_result_with_it_in_place() -> None:
    ctx = lead_run_context(strategy_session=session_with(_strategy(), {}))

    result = await compare_search_variants(
        ctx, [_variant("Minimum 2", min_tm="2"), _variant("Minimum 3", min_tm="3")]
    )

    comparison = returned(result, VariantComparison)
    assert [(v.label, v.gene_count, v.result_count) for v in comparison.variants] == [
        ("Minimum 2", 1490, 227),
        ("Minimum 3", 1029, 82),
    ]
    assert comparison.result_step_id == "step_intersect"


async def test_a_parameter_the_search_does_not_take_is_refused_by_name() -> None:
    ctx = lead_run_context(strategy_session=session_with(_strategy(), {}))

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(
            ctx,
            [
                _variant("Minimum 2", min_tm="2", input="441126163"),
                _variant("Minimum 3", min_tm="3", input="441126163"),
            ],
        )

    assert str(refused.value) == (
        f"{_TM} takes no parameter input (Minimum 2, Minimum 3). The parameters "
        f"it takes: organism, min_tm, max_tm. A step of the strategy is never a "
        f"parameter: each variant is counted in place in the strategy's result."
    )


async def test_a_search_no_step_runs_is_counted_alone() -> None:
    ctx = lead_run_context(strategy_session=session_with(_strategy(), {}))
    ctx.deps.runtime.strategy_session.graph = None

    result = await compare_search_variants(
        ctx, [_variant("Minimum 2", min_tm="2"), _variant("Minimum 3", min_tm="3")]
    )

    comparison = returned(result, VariantComparison)
    assert [v.result_count for v in comparison.variants] == [None, None]
    assert comparison.result_step_id is None


async def test_the_labels_and_counts_a_comparison_returned_are_the_turns() -> None:
    ctx = lead_run_context(strategy_session=session_with(_strategy(), {}))

    await compare_search_variants(
        ctx, [_variant("Minimum 2", min_tm="2"), _variant("Minimum 3", min_tm="3")]
    )

    markers = ctx.deps.state.turn_markers
    assert (markers.compared_labels, set(markers.compared_counts)) == (
        ["Minimum 2", "Minimum 3"],
        {1490, 227, 1029, 82, 0},
    )


_APICOPLAST = (
    "GenesBySubcellularLocalizationpfal3D7_subcellular_localization_"
    "ApicoplastTargeting_RSRC"
)


def _apicoplast_strategy() -> StrategySession:
    session = session_with(
        combine(
            "step_intersect",
            StrategyStepNode(id="step_33f64941", search_name=_APICOPLAST),
            StrategyStepNode(id="step_4dfb1df9", search_name=_TM),
        ),
        {"step_33f64941": 441100001, "step_4dfb1df9": 441100002},
    )
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_33f64941": 441100001, "step_4dfb1df9": 441100002},
        step_counts={"step_33f64941": 495, "step_4dfb1df9": 1490},
        wdk_strategy_id=42,
    )
    return session


async def test_a_search_no_step_runs_is_refused_with_each_steps_search() -> None:
    """A variant is counted in place, so it varies a search a step runs."""
    ctx = lead_run_context(strategy_session=_apicoplast_strategy())
    alone = VariantSpec(
        label="Apicoplast-targeted only",
        search_name="GenesBySubcellularLocalization",
        parameters={},
    )

    with pytest.raises(ModelRetry) as refused:
        await compare_search_variants(ctx, [alone, alone])

    assert str(refused.value) == (
        "GenesBySubcellularLocalization (Apicoplast-targeted only) is no search a "
        "step of this strategy runs, and each variant is counted in place in the "
        "strategy's result. The steps: "
        f"step_33f64941 runs {_APICOPLAST} (495 genes); "
        f"step_4dfb1df9 runs {_TM} (1,490 genes). "
        "The count of a criterion's removal is the count of the step that stays."
    )
