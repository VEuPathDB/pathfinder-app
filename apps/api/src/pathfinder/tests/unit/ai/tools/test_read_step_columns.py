"""A check reads a search step's columns over the whole step, from the site's own
reports, and records each fit for the evidence card."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import StringValue

from pathfinder.ai.tools.standalone import results
from pathfinder.ai.tools.standalone._result_models import NAMED_COLUMNS, StepColumns
from pathfinder.domain.column_fit import ColumnFit
from pathfinder.domain.column_reach import ReachedColumn
from pathfinder.tests._support.column_reads import (
    TM_PARAMS,
    TM_TEXT,
    ColumnSite,
    column_context,
    percentile_context,
    percentile_site,
    serve_columns,
)
from pathfinder.tests._support.recorded_columns import (
    PERCENTILE_SEARCH,
    PERCENTILE_STEP,
    TM_STEP,
    by_value,
)
from pathfinder.tests._support.tool_returns import returned

COUNTS = " Its records count by "
GENE_ID = ReachedColumn(name="primary_key", display_name="Gene ID")


async def test_the_tm_count_column_fits_every_gene_of_the_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = ColumnSite({"tm_count": by_value("step_column_tm_count_by_value")}, {})
    serve_columns(monkeypatch, site)
    ctx = column_context("GenesByTransmembraneDomains", TM_STEP, TM_PARAMS)

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    expected = ColumnFit(
        criterion_id="c_one",
        criterion_text=TM_TEXT,
        wdk_step_id=TM_STEP,
        column="tm_count",
        display_name="# TM Domains",
        bound_value="2 to 99",
        counted_in="transcripts",
        total=840,
        fitting=840,
        fitting_at_most=840,
    )
    assert (
        answer.fits,
        ctx.deps.turn_markers.column_fits,
        site.asked,
        site.budgets,
    ) == (
        [expected],
        [expected],
        [f"{TM_STEP}/columns/tm_count"],
        [results.READ_DEADLINE_SECONDS],
    )


async def test_a_threshold_the_step_holds_on_neither_side_states_both_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = ColumnSite({"tm_count": by_value("step_column_tm_count_by_value")}, {})
    serve_columns(monkeypatch, site)
    ctx = column_context(
        "GenesByTransmembraneDomains",
        TM_STEP,
        {**TM_PARAMS, "min_tm": StringValue(value="5")},
    )

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    assert [(f.fits, f.sentence) for f in ctx.deps.turn_markers.column_fits] == [
        (
            "some",
            (
                "840 of 840 transcripts fit # TM Domains (99 or fewer); 242 to 294 of "
                "840 transcripts hold # TM Domains 5 or more and 546 to 598 hold 5 or "
                "fewer"
            ),
        )
    ]
    assert answer.fits == ctx.deps.turn_markers.column_fits


async def test_rival_search_columns_that_all_hold_every_record_stand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_columns(monkeypatch, percentile_site())

    answer = returned(
        await results.read_step_columns(percentile_context("80"), PERCENTILE_STEP),
        StepColumns,
    )

    assert [(f.column, f.counted_in, f.sentence) for f in answer.fits] == [
        (
            "min_percentile_chosen",
            "transcripts",
            "1103 of 1103 transcripts fit Min %ile (Within Chosen Samples) (80 to 100)",
        ),
        (
            "max_percentile_chosen",
            "transcripts",
            "1103 of 1103 transcripts fit Max %ile (Within Chosen Samples) (80 to 100)",
        ),
    ]


async def test_rival_search_columns_that_disagree_name_the_sample_instead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = percentile_site()
    serve_columns(monkeypatch, site)
    ctx = percentile_context("90")

    answer = returned(
        await results.read_step_columns(ctx, PERCENTILE_STEP), StepColumns
    )

    note, counts = answer.note.split(COUNTS, 1)
    assert (answer.fits, note, ctx.deps.turn_markers.column_fits) == (
        [],
        (
            f"2 columns of {PERCENTILE_SEARCH} may show the bound values and "
            "they do not all hold every gene inside them. Sample the root with "
            "get_sample_records for this criterion."
        ),
        [],
    )
    assert (counts.split(", ")[0], answer.countable[0], len(answer.countable)) == (
        "primary_key (Gene ID)",
        GENE_ID,
        NAMED_COLUMNS,
    )
    assert sorted(site.asked) == [
        f"{PERCENTILE_STEP}/reports/max_percentile_chosen-histogram",
        f"{PERCENTILE_STEP}/reports/min_percentile_chosen-histogram",
    ]


async def test_a_report_of_no_records_is_a_step_of_no_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_columns(monkeypatch, ColumnSite({}, {}))
    ctx = column_context("GenesByTransmembraneDomains", TM_STEP, TM_PARAMS)

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    assert [(f.fits, f.total, f.sentence) for f in answer.fits] == [
        ("none", 0, "0 of 0 transcripts fit # TM Domains (2 to 99)")
    ]
    assert answer.note == ""


async def test_a_search_with_no_column_names_the_sample_instead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = ColumnSite({}, {})
    serve_columns(monkeypatch, site)
    ctx = column_context(
        "GenesByText", TM_STEP, {"text_expression": StringValue(value="kinase")}
    )

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    note, counts = answer.note.split(COUNTS, 1)
    assert (answer.fits, note, site.asked) == (
        [],
        (
            "No column of GenesByText shows a numeric value its criterion "
            "binds. Sample the root with get_sample_records for this criterion."
        ),
        [],
    )
    assert counts.endswith(" more that step_columns lists.")
    assert answer.countable[0] == GENE_ID
