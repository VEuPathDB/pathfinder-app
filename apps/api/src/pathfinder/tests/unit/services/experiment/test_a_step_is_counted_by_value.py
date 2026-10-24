"""A built step is counted by a column the site counts by value through the tool
server's ``count_by_column``: its values ranked, its bins for a number column,
and each way the count is refused named back to the model."""

from __future__ import annotations

import pytest
from veupathdb.domain import WDKHistogramBin, WDKHistogramStatistics
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKRecordType
from veupathdb_mcp.wdk import ColumnCounts, ColumnNotCountedError, CountedValue

from pathfinder.domain.tally_facts import tally_id
from pathfinder.services.experiment.column_tally import ColumnTallyRefusedError
from pathfinder.services.experiment.step_tally import run_step_tally
from pathfinder.tests._support.step_tally_site import (
    STEP,
    TallySite,
    ToolServer,
    counted_step,
    serve,
)

_ORGANISM = WDKRecordType.model_validate(
    {
        "urlSegment": "transcript",
        "attributes": [
            {
                "name": "organism",
                "displayName": "Organism",
                "columnDataType": "STRING",
                "tools": {"reports": ["byValue"], "filters": ["byValue"]},
                "formats": [{"name": "organism-wordCloud", "type": "wordCloud"}],
            },
            {
                "name": "gene_type",
                "displayName": "Gene Type",
                "columnDataType": "STRING",
                "tools": {"reports": ["byValue"], "filters": ["byValue"]},
            },
        ],
    }
)


def _strings(total: int, distinct: int, *values: tuple[str, int]) -> ColumnCounts:
    return ColumnCounts(
        step_id=STEP,
        column="organism",
        display_name="Organism",
        kind="string",
        total_records=total,
        distinct_values=distinct,
        values=tuple(CountedValue(value=v, count=n) for v, n in values),
    )


def _genes(server: ToolServer, monkeypatch: pytest.MonkeyPatch) -> TallySite:
    return serve(monkeypatch, TallySite(_ORGANISM, step_count=412), server)


async def test_a_column_is_counted_by_its_ranked_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ToolServer(
        counts=_strings(
            412,
            2,
            ("<i>Plasmodium falciparum</i> 3D7", 306),
            ("<i>Plasmodium vivax</i> P01", 103),
        )
    )
    site = _genes(server, monkeypatch)

    tally = await run_step_tally(
        counted_step("transcript", "GenesByTaxon", "gene"), "organism", 20
    )

    assert (server.counted, site.reports) == ([("orthomcl", STEP, "organism", 20)], [])
    assert [(row.value, row.count, row.label) for row in tally.rows] == [
        ("Plasmodium falciparum 3D7", 306, ""),
        ("Plasmodium vivax P01", 103, ""),
    ]
    assert (tally.total, tally.distinct) == (412, 2)
    assert (tally.title, tally.column_label) == ("Genes by Organism", "Organism")
    assert tally.id == tally_id("orthomcl", f"step {STEP}", "organism", None)


async def test_a_column_of_the_steps_own_search_is_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = ColumnCounts(
        step_id=STEP,
        column="evalue",
        display_name="E-Value",
        kind="string",
        total_records=3,
        distinct_values=2,
        values=(CountedValue(value="1e-50", count=2), CountedValue(value="0", count=1)),
    )
    server = ToolServer(counts=counts)
    _genes(server, monkeypatch)

    tally = await run_step_tally(
        counted_step("transcript", "GenesBySimilarity", "gene"), "evalue", 20
    )

    assert [(row.value, row.count) for row in tally.rows] == [("1e-50", 2), ("0", 1)]
    assert (tally.title, tally.column_label) == ("Genes by E-Value", "E-Value")


async def test_a_number_column_is_counted_by_every_bin_in_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counts = ColumnCounts(
        step_id=STEP,
        column="tm_count",
        display_name="# TM Domains",
        kind="number",
        total_records=840,
        distinct_values=12,
        bins=(
            WDKHistogramBin(value=40, bin_start="2", bin_end="7", bin_label="[2, 7)"),
            WDKHistogramBin(
                value=600, bin_start="7", bin_end="12", bin_label="[7, 12)"
            ),
        ),
        statistics=WDKHistogramStatistics(
            subset_size=840, num_distinct_values=12, num_missing_cases=200
        ),
    )
    _genes(ToolServer(counts=counts), monkeypatch)

    tally = await run_step_tally(
        counted_step("transcript", "GenesByTransmembraneDomains", "gene"),
        "tm_count",
        1,
    )

    assert [(row.value, row.count) for row in tally.rows] == [
        ("[2, 7)", 40),
        ("[7, 12)", 600),
    ]
    assert (tally.total, tally.distinct) == (840, 2)


async def test_a_report_the_site_refuses_is_a_refusal_naming_its_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ToolServer(refusal=WDKError("Unknown column report", status=422))
    _genes(server, monkeypatch)

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            counted_step("transcript", "GenesByTaxon", "gene"), "organism", 20
        )

    assert str(refused.value) == (
        "The site refused to count organism on step 227284080 (HTTP 422). The "
        "step_columns tool lists the columns this step can be counted by."
    )


async def test_a_server_error_is_no_refusal_and_fails_the_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ToolServer(refusal=WDKError("Request failed after retries: ", status=504))
    _genes(server, monkeypatch)

    with pytest.raises(WDKError) as failed:
        await run_step_tally(
            counted_step("transcript", "GenesByTaxon", "gene"), "organism", 20
        )

    assert failed.value.status == 504


async def test_an_unknown_column_names_the_columns_that_can_be_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    countable = tuple(f"column_{n:02d}" for n in range(23))
    server = ToolServer(
        refusal=ColumnNotCountedError(STEP, "organsim", None, countable)
    )
    _genes(server, monkeypatch)

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            counted_step("transcript", "GenesByTaxon", "gene"), "organsim", 20
        )

    named = ", ".join(countable[:20])
    assert str(refused.value) == (
        "gene records of step 227284080 cannot be counted by organsim: it is not "
        f"a column of the step. The columns it can be counted by: {named}, and 3 "
        "more. The step_columns tool lists the columns this step can be counted by."
    )


async def test_a_step_of_no_records_counts_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _genes(ToolServer(counts=_strings(0, 0)), monkeypatch)

    tally = await run_step_tally(
        counted_step("transcript", "GenesByTaxon", "gene"), "organism", 20
    )

    assert (tally.total, tally.distinct, tally.rows) == (0, 0, [])


async def test_a_column_no_record_holds_a_value_in_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _genes(ToolServer(counts=_strings(412, 0)), monkeypatch)

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            counted_step("transcript", "GenesByTaxon", "gene"), "organism", 20
        )

    assert str(refused.value) == (
        "None of the 412 gene records of step 227284080 has a value for organism "
        "(Organism), so it counts nothing. The step_columns tool lists the columns "
        "this step can be counted by."
    )


async def test_rows_are_named_only_when_every_value_is_a_genome_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mixed = _strings(9, 2, ("pfal", 5), ("Plasmodium vivax P01", 4))
    _genes(ToolServer(counts=mixed), monkeypatch)

    tally = await run_step_tally(
        counted_step("transcript", "GenesByTaxon", "gene"), "organism", 20
    )

    assert [(row.value, row.label) for row in tally.rows] == [
        ("pfal", ""),
        ("Plasmodium vivax P01", ""),
    ]


async def test_genome_codes_are_named_by_their_genome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    codes = _strings(9, 2, ("pfal", 5), ("pviv", 4))
    _genes(ToolServer(counts=codes), monkeypatch)

    tally = await run_step_tally(
        counted_step("transcript", "GenesByTaxon", "gene"), "organism", 20
    )

    assert [(row.value, row.count, row.label) for row in tally.rows] == [
        ("pfal", 5, "Plasmodium falciparum 3D7"),
        ("pviv", 4, "Plasmodium vivax Sal-1"),
    ]
