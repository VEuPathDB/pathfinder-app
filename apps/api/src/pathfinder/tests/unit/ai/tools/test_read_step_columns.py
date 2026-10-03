"""A check reads a search step's columns over the whole step, from the site's own
reports, and records each fit for the evidence card."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import JsonValue
from pydantic_ai import RunContext, ToolFailed
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb.domain.strategy import StrategyStepNode, flatten_tree
from veupathdb.errors import WDKError
from veupathdb.wdk import (
    WDKColumnDistribution,
    WDKRecordType,
    WDKSearch,
    WDKSearchResponse,
)

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.tools.standalone import results
from pathfinder.ai.tools.standalone._result_models import StepColumns
from pathfinder.domain.evidence import ColumnFit
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.value_binding import bind_values
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.recorded_columns import (
    PERCENTILE_SEARCH,
    PERCENTILE_STEP,
    TM_STEP,
    by_value,
    catalog_search,
    column_catalog,
    recorded_body,
)
from pathfinder.tests._support.tool_returns import returned

from .conftest import agent_run_context

_TM_TEXT = "two or more transmembrane domains"


class _Site:
    """The site's column reports, answered from the recorded bodies."""

    def __init__(
        self,
        columns: Mapping[str, WDKColumnDistribution],
        reports: Mapping[str, JsonValue],
    ) -> None:
        self.columns = columns
        self.reports = reports
        self.asked: list[str] = []

    async def get_column_distribution(
        self, step_id: int, column_name: str
    ) -> WDKColumnDistribution:
        self.asked.append(f"{step_id}/columns/{column_name}")
        return self.columns.get(column_name, WDKColumnDistribution())

    async def run_step_report(self, step_id: int, report_name: str) -> JsonValue:
        self.asked.append(f"{step_id}/reports/{report_name}")
        return self.reports[report_name]


# The parameter types plasmodb reports: every numeric threshold is a string
# that is a number, and a text expression is a string that is not.
_NUMERIC = frozenset(
    {"min_tm", "max_tm", "min_expression_percentile", "max_expression_percentile"}
)


class _Definitions:
    """The expanded search definitions, with the parameters the tests bind."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    async def get_search_details(self, ctx: SearchContext) -> WDKSearchResponse:
        self.asked.append(ctx.search_name)
        search = catalog_search(ctx.search_name)
        return WDKSearchResponse.model_validate(
            {
                "searchData": {
                    "urlSegment": search.url_segment,
                    "parameters": [
                        {"name": n, "type": "string", "isNumber": n in _NUMERIC}
                        for n in search.param_names
                    ],
                },
                "validation": {"level": "DISPLAYABLE", "isValid": True},
            }
        )


def _serve(monkeypatch: pytest.MonkeyPatch, site: _Site) -> None:
    catalog = column_catalog()
    definitions = _Definitions()

    async def searches(site_id: str, record_type: str) -> list[WDKSearch]:
        del site_id, record_type
        return list(catalog.searches or [])

    async def record_types(site_id: str) -> list[WDKRecordType]:
        del site_id
        return [catalog]

    monkeypatch.setattr(results, "get_raw_searches", searches)
    monkeypatch.setattr(results, "get_raw_record_types", record_types)
    monkeypatch.setattr(results, "get_strategy_api", lambda site_id: site)
    monkeypatch.setattr(results, "get_discovery_service", lambda: definitions)


def _context(
    search_name: str,
    wdk_step_id: int,
    params: Mapping[str, ParamValue],
    counted: int | None = None,
) -> RunContext[AgentDeps]:
    session = StrategySession(site_id="plasmodb")
    graph = StrategyGraph(graph_id="g1", name="Membrane", site_id="plasmodb")
    graph.record_type = "transcript"
    graph.steps = flatten_tree(StrategyStepNode(id="c_one", search_name=search_name))
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={"c_one": wdk_step_id}, step_counts={"c_one": counted}
    )
    criterion = Criterion(
        id="c_one",
        text=_TM_TEXT,
        search_name=search_name,
        resolved_params=bind_values(params, "stated", []),
    )
    state = AgentToolState(operational_spec_draft=OperationalSpec(criteria=[criterion]))
    return agent_run_context(strategy_session=session, agent_state=state)


_TM: dict[str, ParamValue] = {
    "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"]),
    "min_tm": StringValue(value="2"),
    "max_tm": StringValue(value="99"),
}


async def test_the_tm_count_column_fits_every_gene_of_the_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _Site({"tm_count": by_value("step_column_tm_count_by_value")}, {})
    _serve(monkeypatch, site)
    ctx = _context("GenesByTransmembraneDomains", TM_STEP, _TM)

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    expected = ColumnFit(
        criterion_id="c_one",
        criterion_text=_TM_TEXT,
        wdk_step_id=TM_STEP,
        column="tm_count",
        display_name="# TM Domains",
        bound_value="2 to 99",
        total=840,
        fitting=840,
        fitting_at_most=840,
    )
    assert (answer.fits, ctx.deps.turn_markers.column_fits, site.asked) == (
        [expected],
        [expected],
        [f"{TM_STEP}/columns/tm_count"],
    )


async def test_a_threshold_the_step_holds_on_neither_side_states_both_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _Site({"tm_count": by_value("step_column_tm_count_by_value")}, {})
    _serve(monkeypatch, site)
    ctx = _context(
        "GenesByTransmembraneDomains",
        TM_STEP,
        {**_TM, "min_tm": StringValue(value="5")},
    )

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    assert [(f.fits, f.sentence) for f in ctx.deps.turn_markers.column_fits] == [
        (
            "some",
            (
                "840 of 840 genes fit # TM Domains (99 or fewer); 242 to 294 of 840 "
                "genes hold # TM Domains 5 or more and 546 to 598 hold 5 or fewer"
            ),
        )
    ]
    assert answer.fits == ctx.deps.turn_markers.column_fits


def _percentile_site() -> _Site:
    return _Site(
        {},
        {
            "min_percentile_chosen-histogram": recorded_body(
                "step_report_min_percentile_chosen_histogram"
            ),
            "max_percentile_chosen-histogram": recorded_body(
                "step_report_max_percentile_chosen_histogram"
            ),
        },
    )


def _percentile_context(low: str) -> RunContext[AgentDeps]:
    return _context(
        PERCENTILE_SEARCH,
        PERCENTILE_STEP,
        {
            "min_expression_percentile": StringValue(value=low),
            "max_expression_percentile": StringValue(value="100"),
        },
    )


async def test_rival_search_columns_that_all_hold_every_record_stand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _percentile_site())

    answer = returned(
        await results.read_step_columns(_percentile_context("80"), PERCENTILE_STEP),
        StepColumns,
    )

    assert [(f.column, f.counted_in, f.sentence) for f in answer.fits] == [
        (
            "min_percentile_chosen",
            "transcripts",
            "1663 of 1663 transcripts fit Min %ile (Within Chosen Samples) (80 to 100)",
        ),
        (
            "max_percentile_chosen",
            "transcripts",
            "1663 of 1663 transcripts fit Max %ile (Within Chosen Samples) (80 to 100)",
        ),
    ]


async def test_rival_search_columns_that_disagree_name_the_sample_instead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _percentile_site()
    _serve(monkeypatch, site)
    ctx = _percentile_context("90")

    answer = returned(
        await results.read_step_columns(ctx, PERCENTILE_STEP), StepColumns
    )

    assert (answer.fits, answer.note, ctx.deps.turn_markers.column_fits) == (
        [],
        (
            f"2 columns of {PERCENTILE_SEARCH} may show the bound values and "
            "they do not all hold every gene inside them. Sample the root with "
            "get_sample_records for this criterion."
        ),
        [],
    )
    assert sorted(site.asked) == [
        f"{PERCENTILE_STEP}/reports/max_percentile_chosen-histogram",
        f"{PERCENTILE_STEP}/reports/min_percentile_chosen-histogram",
    ]


async def test_a_column_the_site_does_not_report_is_not_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _Site({}, {}))
    ctx = _context("GenesByTransmembraneDomains", TM_STEP, _TM)

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    assert [(f.fits, f.sentence) for f in answer.fits] == [
        ("not_shown", f"the site shows no column for '{_TM_TEXT}'")
    ]


async def test_a_read_with_no_rows_on_a_counted_step_names_the_step_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The column the search publishes is not reported as absent."""
    site = _Site({}, {})
    _serve(monkeypatch, site)
    ctx = _context(
        "GenesByTransmembraneDomains",
        TM_STEP,
        {"min_tm": StringValue(value="0"), "max_tm": StringValue(value="0")},
        counted=5041,
    )

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    assert (answer.fits, answer.note, ctx.deps.turn_markers.column_fits) == (
        [],
        (
            f"Step {TM_STEP} counts 5041 on the site and its read of "
            "# TM Domains (tm_count) returned no rows. Sample step "
            f"{TM_STEP} with get_sample_records and read tm_count on its "
            "records for this criterion."
        ),
        [],
    )
    assert site.asked == [f"{TM_STEP}/columns/tm_count"]


async def test_a_search_with_no_column_names_the_sample_instead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _Site({}, {})
    _serve(monkeypatch, site)
    ctx = _context(
        "GenesByText", TM_STEP, {"text_expression": StringValue(value="kinase")}
    )

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    assert (answer.fits, answer.note, site.asked) == (
        [],
        (
            "No column of GenesByText shows a numeric value its criterion "
            "binds. Sample the root with get_sample_records for this criterion."
        ),
        [],
    )


class _BrokenSite(_Site):
    """A site that breaks off every column report."""

    async def get_column_distribution(
        self, step_id: int, column_name: str
    ) -> WDKColumnDistribution:
        del step_id, column_name
        msg = "Request failed after retries: "
        raise WDKError(msg, status=504)


async def test_a_column_read_the_site_breaks_off_fails_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed call is not held as answered and names the site's status."""
    _serve(monkeypatch, _BrokenSite({}, {}))
    ctx = _context("GenesByTransmembraneDomains", TM_STEP, _TM)

    with pytest.raises(ToolFailed) as failed:
        await results.read_step_columns(ctx, TM_STEP)

    assert failed.value.message.startswith(
        "read_step_columns got no answer from the site (HTTP 504: VEuPathDB service "
        "error: Request failed after retries:)."
    )
    assert ctx.deps.turn_markers.column_fits == []
