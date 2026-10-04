"""read_eda_statistics shows what the EDA service computed on the open analysis,
files it as a fact, and refuses a request the study cannot answer."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.ui.vercel_ai.response_types import DataChunk
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import EdaAnalysisDetail

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_statistics
from pathfinder.ai.tools.standalone.eda_compute import EdaVariableSpecIn
from pathfinder.ai.tools.standalone.eda_statistics import EdaStatisticResult
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.domain.statistic_facts import StatisticRowFact
from pathfinder.tests._support.eda_step_doubles import (
    COUNTS_ENTITY,
    DE_DATASET,
    SAMPLE_ENTITY,
    TEMPERATURE_VARIABLE,
    binding_of,
    de_analysis,
    de_study,
)
from pathfinder.tests._support.eda_wire import DE_STUDY, eda_transport, wire_eda
from pathfinder.tests._support.tool_returns import returned

_GENOTYPE = EdaVariableSpecIn(entity_id=SAMPLE_ENTITY, variable_id="VAR_84f17484")
_CONDITION = EdaVariableSpecIn(
    entity_id=SAMPLE_ENTITY, variable_id=TEMPERATURE_VARIABLE
)
_SENSE = EdaVariableSpecIn(
    entity_id=COUNTS_ENTITY, variable_id="SEQUENCE_READ_COUNT_SENSE"
)
_ANTISENSE = EdaVariableSpecIn(
    entity_id=COUNTS_ENTITY, variable_id="SEQUENCE_READ_COUNT_ANTISENSE"
)


def _statistic(value: float, pvalue: str, interval: str) -> dict[str, object]:
    return {
        "value": value,
        "pvalue": pvalue,
        "confidenceInterval": interval,
        "confidenceLevel": 0.95,
    }


# The 2x2 answer as the library's own hermetic suite builds it: the mosaic counts
# and one statistics row, under the names the service's R package writes.
_TWO_BY_TWO = {
    "mosaic": {
        "data": [
            {
                "xLabel": ["febrile", "normal"],
                "yLabel": [["wildtype", "delta-DHC mutant"]] * 2,
                "value": [[3, 1], [1, 3]],
            }
        ],
        "config": {"variables": [], "completeCasesAllVars": 8},
    },
    "statsTable": [
        {
            "chiSq": _statistic(0.5, "0.4795", "NA"),
            "fisher": _statistic(9.0, "0.4857", "0.3 - 271.9"),
            "oddsRatio": _statistic(9.0, "0.4857", "0.3 - 271.9"),
            "relativeRisk": _statistic(3.0, "0.4857", "0.5 - 18.1"),
        }
    ],
    "sampleSizeTable": [],
    "completeCasesTable": [],
}
_UNEVALUATED = {
    "status": "bad-request",
    "message": "eval failed, request status: error code: 127",
}


@pytest.fixture(autouse=True)
def token() -> Iterator[None]:
    handle = veupathdb_auth_token_ctx.set("t")
    yield
    veupathdb_auth_token_ctx.reset(handle)


@pytest.fixture
def two_by_two() -> list[httpx.Response]:
    """The service's answer to a two-by-two request."""
    return [httpx.Response(200, json=_TWO_BY_TWO)]


@pytest.fixture(autouse=True)
def recorded(monkeypatch: pytest.MonkeyPatch, two_by_two: list[httpx.Response]) -> None:
    """The recorded RNA-Seq study, its plots, and a thread bound to it."""
    inner = eda_transport(study_id=DE_STUDY, study_fixture="study_detail_de")

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/visualizations/twobytwo"):
            return two_by_two[0]
        return inner.handle_request(request)

    wire_eda(monkeypatch, httpx.MockTransport(handle))
    detail = de_analysis(filters=[])

    async def bound(_ctx: object) -> ConversationAnalysisView:
        return binding_of(detail)

    async def read(_site: str, *, analysis_id: str) -> EdaAnalysisDetail:
        assert analysis_id == detail.analysis_id
        return detail

    monkeypatch.setattr(eda_statistics, "bound_analysis", bound)
    monkeypatch.setattr(eda_statistics, "read_analysis", read)
    monkeypatch.setattr(eda_statistics, "get_study_detail_for_dataset", de_study)


def _parts(metadata: Any) -> list[dict[str, Any]]:
    return [
        chunk.data
        for chunk in metadata
        if isinstance(chunk, DataChunk) and chunk.type == "data-eda.statistics"
    ]


async def test_a_contingency_table_shows_the_service_s_chi_squared(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    answer = await eda_statistics.read_eda_statistics(
        lead_ctx,
        kind="contingency",
        x_variable=_GENOTYPE,
        y_variable=_CONDITION,
        output_entity_id=SAMPLE_ENTITY,
        caption="Each genotype was sampled in both conditions",
    )

    (part,) = _parts(answer.metadata)
    assert part["datasetId"] == DE_DATASET
    assert part["kind"] == "contingency"
    assert part["title"] == "Contingency table of genotype by temperature_condition"
    assert part["rows"] == [
        {
            "name": "chi-squared",
            "value": "0",
            "pValue": "1",
            "confidenceInterval": None,
        },
        {
            "name": "degrees of freedom",
            "value": "2",
            "pValue": None,
            "confidenceInterval": None,
        },
    ]
    assert part["table"] == {
        "xLabels": ["delta-DHC mutant", "delta-LRR5 mutant", "wildtype"],
        "yLabels": ["febrile", "normal"],
        "matrix": [[2, 2], [2, 2], [2, 2]],
    }
    assert part["caption"] == "Each genotype was sampled in both conditions"
    statistic = returned(answer, EdaStatisticResult).statistic
    assert statistic.rows == [
        StatisticRowFact(name="chi-squared", value="0"),
        StatisticRowFact(name="chi-squared p-value", value="1"),
        StatisticRowFact(name="degrees of freedom", value="2"),
    ]
    assert lead_ctx.deps.state.domain.statistics == [statistic]


async def test_a_boxplot_shows_each_group_s_five_numbers(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    answer = await eda_statistics.read_eda_statistics(
        lead_ctx,
        kind="boxplot",
        x_variable=_GENOTYPE,
        y_variable=_SENSE,
        output_entity_id=COUNTS_ENTITY,
    )

    (part,) = _parts(answer.metadata)
    assert part["title"] == "Box plot of Sense Count by genotype"
    assert [
        (b["label"], b["median"], b["q3"], b["mean"], b["outlierCount"])
        for b in part["boxes"]
    ] == [
        ("delta-DHC mutant", 1.0, 4.5, 61.1667, 4),
        ("delta-LRR5 mutant", 1.0, 5.25, 52.4583, 4),
        ("wildtype", 13.5, 45.5, 76.7083, 4),
    ]
    assert part["rows"] == []


async def test_a_trend_shows_the_line_the_service_fit_and_its_r_squared(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    answer = await eda_statistics.read_eda_statistics(
        lead_ctx,
        kind="trend",
        x_variable=_SENSE,
        y_variable=_ANTISENSE,
        output_entity_id=COUNTS_ENTITY,
    )

    (part,) = _parts(answer.metadata)
    assert [(r["name"], r["value"]) for r in part["rows"]] == [
        ("r-squared", "0.106"),
        ("points", "36 points"),
    ]
    assert part["trend"]["lineY"][:2] == [5.5487, 5.5713]
    assert len(part["trend"]["x"]) == 36
    assert (part["trend"]["xLabel"], part["trend"]["yLabel"]) == (
        "Sense Count",
        "Antisense Count",
    )


async def _two_by_two(lead_ctx: RunContext[LeadDeps]) -> Any:
    return await eda_statistics.read_eda_statistics(
        lead_ctx,
        kind="two_by_two",
        x_variable=_CONDITION,
        y_variable=_GENOTYPE,
        output_entity_id=SAMPLE_ENTITY,
        x_reference_value="febrile",
        y_reference_value="wildtype",
    )


async def test_a_two_by_two_lists_every_statistic_the_service_returned(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    answer = await _two_by_two(lead_ctx)

    (part,) = _parts(answer.metadata)
    assert part["title"] == "Two-by-two table of temperature_condition by genotype"
    assert [
        (r["name"], r["value"], r["pValue"], r["confidenceInterval"])
        for r in part["rows"]
    ] == [
        ("chi-squared", "0.5", "0.4795", "NA"),
        ("Fisher's exact", "9", "0.4857", "0.3 - 271.9"),
        ("odds ratio", "9", "0.4857", "0.3 - 271.9"),
        ("relative risk", "3", "0.4857", "0.5 - 18.1"),
    ]
    assert part["table"] == {
        "xLabels": ["febrile", "normal"],
        "yLabels": ["wildtype", "delta-DHC mutant"],
        "matrix": [[3, 1], [1, 3]],
    }


async def test_a_two_by_two_the_site_cannot_evaluate_points_at_the_contingency(
    lead_ctx: RunContext[LeadDeps], two_by_two: list[httpx.Response]
) -> None:
    two_by_two[0] = httpx.Response(400, json=_UNEVALUATED)

    with pytest.raises(ModelRetry) as refused:
        await _two_by_two(lead_ctx)

    assert str(refused.value) == (
        "The site cannot compute a two-by-two table on this study. The "
        "contingency table of the same two variables answers chi-squared, "
        "degrees of freedom and p. Nothing was computed."
    )
    assert lead_ctx.deps.state.domain.statistics == []


async def test_a_two_by_two_without_its_reference_values_is_refused(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    with pytest.raises(ModelRetry) as refused:
        await eda_statistics.read_eda_statistics(
            lead_ctx,
            kind="two_by_two",
            x_variable=_CONDITION,
            y_variable=_GENOTYPE,
            output_entity_id=SAMPLE_ENTITY,
        )

    assert str(refused.value) == (
        "A two-by-two table needs x_reference_value and y_reference_value: the "
        "exposed x value and the positive y value. Nothing was computed."
    )


async def test_a_variable_below_the_counted_entity_is_refused(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    with pytest.raises(ModelRetry) as refused:
        await eda_statistics.read_eda_statistics(
            lead_ctx,
            kind="boxplot",
            x_variable=_GENOTYPE,
            y_variable=_SENSE,
            output_entity_id=SAMPLE_ENTITY,
        )

    assert str(refused.value) == (
        f"{COUNTS_ENTITY} is not {SAMPLE_ENTITY} or an ancestor of it, so a "
        f"boxplot of {SAMPLE_ENTITY} cannot read SEQUENCE_READ_COUNT_SENSE. The "
        f"readable entities are {SAMPLE_ENTITY}. Nothing was computed."
    )
    assert lead_ctx.deps.state.domain.statistics == []


async def test_a_color_on_a_statistic_that_has_none_is_refused(
    lead_ctx: RunContext[LeadDeps],
) -> None:
    with pytest.raises(ModelRetry) as refused:
        await eda_statistics.read_eda_statistics(
            lead_ctx,
            kind="contingency",
            x_variable=_GENOTYPE,
            y_variable=_CONDITION,
            output_entity_id=SAMPLE_ENTITY,
            color_by_variable=_CONDITION,
        )

    assert str(refused.value) == (
        "color_by_variable groups a boxplot; a contingency has none. Nothing was "
        "computed."
    )


async def test_a_thread_with_no_open_analysis_names_the_tool_that_opens_one(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    async def unbound(_ctx: object) -> None:
        return None

    monkeypatch.setattr(eda_statistics, "bound_analysis", unbound)

    with pytest.raises(ModelRetry) as refused:
        await eda_statistics.read_eda_statistics(
            lead_ctx,
            kind="contingency",
            x_variable=_GENOTYPE,
            y_variable=_CONDITION,
            output_entity_id=SAMPLE_ENTITY,
        )

    assert str(refused.value) == (
        "This conversation has no study open, so there is no subset to compute "
        "on. Call open_eda_analysis first."
    )
