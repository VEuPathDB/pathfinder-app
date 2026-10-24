"""A column report the site refuses, or one no record holds a value of, is
stated with the step to sample, and a server error fails the read."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from pydantic import JsonValue
from pydantic_ai import ToolFailed
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKColumnDistribution

from pathfinder.ai.tools.standalone import results
from pathfinder.ai.tools.standalone._result_models import StepColumns
from pathfinder.tests._support.column_reads import (
    TM_PARAMS,
    TM_TEXT,
    ColumnSite,
    column_context,
    percentile_context,
    percentile_site,
    serve_columns,
)
from pathfinder.tests._support.recorded_columns import PERCENTILE_STEP, TM_STEP
from pathfinder.tests._support.tool_returns import returned


def _tm_report(
    subset: int, valued: int, bins: list[tuple[int, str, str]]
) -> ColumnSite:
    return ColumnSite(
        {
            "tm_count": WDKColumnDistribution.model_validate(
                {
                    "statistics": {"subsetSize": subset, "numVarValues": valued},
                    "histogram": [
                        {"value": n, "binStart": start, "binEnd": end}
                        for n, start, end in bins
                    ],
                }
            )
        },
        {},
    )


_SAMPLE_TM = (
    f"Sample step {TM_STEP} with get_sample_records and read tm_count on its "
    "records for this criterion."
)
_NO_TM_VALUE = f"No record of step {TM_STEP} holds a value of # TM Domains (tm_count). {_SAMPLE_TM}"
_REFUSED_TM = (
    f"The site refused the report of # TM Domains (tm_count) on step {TM_STEP} "
    f"(HTTP 422). {_SAMPLE_TM}"
)


async def test_a_column_no_record_holds_a_value_of_names_the_step_to_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_columns(monkeypatch, _tm_report(840, 0, []))
    ctx = column_context("GenesByTransmembraneDomains", TM_STEP, TM_PARAMS)

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    assert [(f.fits, f.total, f.no_value, f.sentence) for f in answer.fits] == [
        (
            "none",
            840,
            840,
            "0 of 840 transcripts fit # TM Domains (2 to 99); 840 hold no value",
        )
    ]
    assert answer.note == _NO_TM_VALUE


async def test_records_with_no_value_are_counted_in_the_step_and_stated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_columns(monkeypatch, _tm_report(840, 740, [(740, "2.0", "3.0")]))
    ctx = column_context("GenesByTransmembraneDomains", TM_STEP, TM_PARAMS)

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    assert [(f.fits, f.total, f.fitting, f.sentence) for f in answer.fits] == [
        (
            "some",
            840,
            740,
            "740 of 840 transcripts fit # TM Domains (2 to 99); 100 hold no value",
        )
    ]
    assert answer.note == ""


class _RefusingSite(ColumnSite):
    """A site that answers every column report with one error status, and the
    step reports it names with a refusal."""

    def __init__(
        self,
        columns: Mapping[str, WDKColumnDistribution],
        reports: Mapping[str, JsonValue],
        refused: frozenset[str],
        status: int = 400,
    ) -> None:
        super().__init__(columns, reports)
        self.refused = refused
        self.status = status

    async def get_column_distribution(
        self, step_id: int, column_name: str, *, budget_seconds: float | None = None
    ) -> WDKColumnDistribution:
        del budget_seconds
        self.asked.append(f"{step_id}/columns/{column_name}")
        msg = "Request failed after retries: "
        raise WDKError(msg, status=self.status)

    async def run_step_report(self, step_id: int, report_name: str) -> JsonValue:
        if report_name in self.refused:
            self.asked.append(f"{step_id}/reports/{report_name}")
            msg = "Unknown report"
            raise WDKError(msg, status=400)
        return await super().run_step_report(step_id, report_name)


async def test_a_column_the_site_refuses_is_an_unread_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _RefusingSite({}, {}, frozenset(), status=422)
    serve_columns(monkeypatch, site)
    ctx = column_context("GenesByTransmembraneDomains", TM_STEP, TM_PARAMS)

    answer = returned(await results.read_step_columns(ctx, TM_STEP), StepColumns)

    refused = (
        "not_shown",
        422,
        (
            "the site refused the # TM Domains (tm_count) column (HTTP 422) for "
            f"'{TM_TEXT}'"
        ),
    )
    assert [(f.fits, f.refused_status, f.sentence) for f in answer.fits] == [refused]
    assert [
        (f.fits, f.refused_status, f.sentence)
        for f in ctx.deps.turn_markers.column_fits
    ] == [refused]
    assert answer.note == _REFUSED_TM
    assert site.asked == [f"{TM_STEP}/columns/tm_count"]


async def test_a_column_read_the_site_breaks_off_fails_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A server error is no refusal: the call fails and names the status."""
    serve_columns(monkeypatch, _RefusingSite({}, {}, frozenset(), status=504))
    ctx = column_context("GenesByTransmembraneDomains", TM_STEP, TM_PARAMS)

    with pytest.raises(ToolFailed) as failed:
        await results.read_step_columns(ctx, TM_STEP)

    assert failed.value.message.startswith(
        "read_step_columns got no answer from the site (HTTP 504: VEuPathDB service "
        "error: Request failed after retries:)."
    )
    assert ctx.deps.turn_markers.column_fits == []


async def test_a_refused_rival_column_leaves_the_others_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = percentile_site()
    site = _RefusingSite(
        base.columns, base.reports, frozenset({"max_percentile_chosen-histogram"})
    )
    serve_columns(monkeypatch, site)

    answer = returned(
        await results.read_step_columns(percentile_context("80"), PERCENTILE_STEP),
        StepColumns,
    )

    assert [(f.column, f.fits, f.sentence) for f in answer.fits] == [
        (
            "min_percentile_chosen",
            "all",
            "1103 of 1103 transcripts fit Min %ile (Within Chosen Samples) (80 to 100)",
        ),
        (
            "max_percentile_chosen",
            "not_shown",
            (
                "the site refused the Max %ile (Within Chosen Samples) "
                "(max_percentile_chosen) column (HTTP 400) for "
                f"'{TM_TEXT}'"
            ),
        ),
    ]
    assert answer.note == (
        "The site refused the report of Max %ile (Within Chosen Samples) "
        f"(max_percentile_chosen) on step {PERCENTILE_STEP} (HTTP 400). Sample step "
        f"{PERCENTILE_STEP} with get_sample_records and read max_percentile_chosen "
        "on its records for this criterion."
    )
    assert sorted(site.asked) == [
        f"{PERCENTILE_STEP}/reports/max_percentile_chosen-histogram",
        f"{PERCENTILE_STEP}/reports/min_percentile_chosen-histogram",
    ]
