"""A built step is counted by one column: a column of genome codes the site
counts only by its word cloud is counted by it when the words are the records,
and every other column goes to the tool server."""

from __future__ import annotations

import pytest
from veupathdb.wdk import WDKRecordType
from veupathdb_mcp.wdk import ColumnNotCountedError, StepColumn, StepColumns

from pathfinder.domain.tally_facts import tally_id
from pathfinder.services.experiment.column_tally import ColumnTallyRefusedError
from pathfinder.services.experiment.step_tally import (
    countable_columns,
    run_step_tally,
)
from pathfinder.tests._support.step_tally_site import (
    STEP,
    STEP_URL,
    TallySite,
    ToolServer,
    counted_step,
    sequence_record_type,
    serve,
    singleton_counts,
)

_LISTED = "The step_columns tool lists the columns this step can be counted by."


def _singletons(
    monkeypatch: pytest.MonkeyPatch,
    *,
    step_count: int,
    server: ToolServer | None = None,
) -> TallySite:
    return serve(
        monkeypatch,
        TallySite(
            sequence_record_type(),
            step_count=step_count,
            words=singleton_counts().model_dump(mode="json"),
        ),
        server or ToolServer(),
    )


def _no_count(column: str) -> ToolServer:
    return ToolServer(refusal=ColumnNotCountedError(STEP, column, "NUMBER", ()))


async def test_the_proteins_of_a_step_are_counted_per_genome_by_their_word_cloud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ToolServer()
    site = _singletons(monkeypatch, step_count=523795, server=server)

    tally = await run_step_tally(
        counted_step("sequence", "FromGroups", "protein", STEP_URL), "abbreviation", 200
    )

    assert (site.reports, server.counted) == ([(STEP, "abbreviation-wordCloud")], [])
    assert (tally.total, tally.distinct, len(tally.rows)) == (523795, 840, 200)
    assert [(row.value, row.count) for row in tally.rows[:10]] == [
        ("bpli", 18260),
        ("osat", 9365),
        ("tvag", 9301),
        ("bpfe", 7194),
        ("ppat", 7066),
        ("tetr", 6730),
        ("gthe", 6254),
        ("asic", 6205),
        ("cvel", 5827),
        ("sarc", 5773),
    ]
    assert tally.rows[0].label.startswith("Brachionus plicatilis")
    assert tally.title == "Proteins by Taxon Code"
    assert (tally.site_id, tally.step_url, tally.column_label) == (
        "orthomcl",
        STEP_URL,
        "Taxon Code",
    )
    assert tally.id == tally_id("orthomcl", f"step {STEP}", "abbreviation", None)
    assert tally.fact().count("bpli") == 18260


async def test_a_word_cloud_count_keeps_the_top_values_asked_for(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _singletons(monkeypatch, step_count=523795)

    tally = await run_step_tally(
        counted_step("sequence", "FromGroups", "protein"), "abbreviation", 3
    )

    assert [(row.value, row.count) for row in tally.rows] == [
        ("bpli", 18260),
        ("osat", 9365),
        ("tvag", 9301),
    ]
    assert tally.distinct == 840


async def test_the_listed_columns_count_a_genome_code_column_by_its_word_cloud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listed = StepColumns(
        step_id=STEP,
        record_type="sequence",
        search_name="FromGroups",
        columns=(
            StepColumn(
                name="abbreviation",
                display_name="Taxon Code",
                data_type="STRING",
                countable=False,
            ),
            StepColumn(
                name="taxon_name",
                display_name="Taxon Name",
                data_type="STRING",
                countable=False,
            ),
            StepColumn(
                name="length", display_name="Length", data_type="NUMBER", countable=True
            ),
        ),
    )
    server = ToolServer(listed=listed)
    _singletons(monkeypatch, step_count=1, server=server)

    columns = await countable_columns("orthomcl", STEP)

    assert server.listed_for == [("orthomcl", STEP)]
    assert [(c.name, c.countable) for c in columns.columns] == [
        ("abbreviation", True),
        ("taxon_name", False),
        ("length", True),
    ]
    assert (columns.record_type, columns.search_name) == ("sequence", "FromGroups")


async def test_word_counts_that_are_not_the_steps_records_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _singletons(monkeypatch, step_count=523796)

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            counted_step("sequence", "FromGroups", "protein"), "abbreviation", 200
        )

    message = str(refused.value)
    assert "523,796 protein records" in message
    assert "sum to 523,795" in message
    assert message.startswith("abbreviation (Taxon Code) cannot count the 523,796")


async def test_a_column_with_no_count_is_refused_with_the_columns_that_have_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = _no_count("length")
    site = _singletons(monkeypatch, step_count=523795, server=server)

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            counted_step("sequence", "FromGroups", "protein"), "length", 200
        )

    assert str(refused.value) == (
        "protein records of step 227284080 cannot be counted by length: the site "
        "has no count of its NUMBER values. The columns it can be counted by: "
        "abbreviation."
    )
    assert (server.counted, site.reports) == ([("orthomcl", STEP, "length", 200)], [])


async def test_a_column_refused_in_this_pass_is_not_offered_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _singletons(monkeypatch, step_count=523795, server=_no_count("length"))

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            counted_step(
                "sequence", "FromGroups", "protein", refused=frozenset({"abbreviation"})
            ),
            "length",
            200,
        )

    assert str(refused.value) == (
        "protein records of step 227284080 cannot be counted by length: the site "
        "has no count of its NUMBER values. No other column of these records can "
        "be counted."
    )


async def test_a_word_cloud_column_that_holds_no_genome_codes_is_refused_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ToolServer()
    site = _singletons(monkeypatch, step_count=523795, server=server)

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            counted_step("sequence", "FromGroups", "protein"), "taxon_name", 200
        )

    assert str(refused.value) == (
        "taxon_name (Taxon Name) cannot be counted on step 227284080: the site "
        "counts it only by its word cloud, which splits and folds values into "
        f"words, so only a column of genome codes is counted that way. {_LISTED}"
    )
    assert (site.reports, server.counted) == ([], [])


async def test_a_record_type_with_no_countable_column_says_so(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_type = WDKRecordType.model_validate(
        {
            "urlSegment": "sequence",
            "attributes": [
                {
                    "name": "length",
                    "displayName": "Length",
                    "columnDataType": "NUMBER",
                    "formats": [{"name": "length-histogram", "type": "histogram"}],
                }
            ],
        }
    )
    serve(monkeypatch, TallySite(record_type, step_count=1), _no_count("length"))

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            counted_step("sequence", "FromGroups", "protein"), "length", 200
        )

    assert str(refused.value).endswith(
        "No other column of these records can be counted."
    )


async def test_a_word_cloud_at_the_sites_cap_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve(
        monkeypatch,
        TallySite(
            sequence_record_type(),
            step_count=523795,
            words={"tags": [{"word": "Too many words", "count": 1}]},
        ),
        ToolServer(),
    )

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            counted_step("sequence", "FromGroups", "protein"), "abbreviation", 200
        )

    message = str(refused.value)
    assert message.startswith(
        "abbreviation (Taxon Code) cannot be counted on step 227284080: the site's "
        "word cloud answered no counts ("
    )
    assert "cap of 10,000 distinct words" in message
    assert message.endswith(_LISTED)


async def test_words_that_are_not_genome_codes_are_refused_though_they_sum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = serve(
        monkeypatch,
        TallySite(
            sequence_record_type(),
            step_count=2,
            words={"tags": [{"word": "kinase", "count": 2}]},
        ),
        ToolServer(),
    )

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            counted_step("sequence", "FromGroups", "protein"), "abbreviation", 200
        )

    assert str(refused.value) == (
        "abbreviation (Taxon Code) cannot be counted on step 227284080: the site "
        "counts it only by its word cloud, which splits and folds values into words, "
        "so its counts are taken only when every word is a genome code, and kinase "
        f"is not. {_LISTED}"
    )
    assert site.reports == [(STEP, "abbreviation-wordCloud")]
