"""A built step is counted by one column: with the site's byValue reporter where
the column offers it, else with its word cloud when the words are the records."""

from __future__ import annotations

import pytest
from pydantic import JsonValue
from veupathdb.errors import validate_response
from veupathdb.testing.wdk_fixtures import RecordedWDKResponse
from veupathdb.wdk import WDKColumnDistribution, WDKRecordType, WDKWordCounts

from pathfinder.domain.tally_facts import tally_id
from pathfinder.services.experiment import step_tally
from pathfinder.services.experiment.column_tally import ColumnTallyRefusedError
from pathfinder.services.experiment.step_tally import CountedStep, run_step_tally
from pathfinder.tests._support.ortho_taxonomy import recorded_ortho_taxonomy
from pathfinder.tests._support.qa_recording import SUITE_WDK_STORE, qa_recording

_STEP = 227284080
_STEP_URL = "https://qa.orthomcl.org/orthomcl.qa/app/workspace/strategies/1/227284080"


def _step(
    record_type: str,
    search_name: str,
    noun: str,
    step_url: str | None,
    refused: frozenset[str] = frozenset(),
) -> CountedStep:
    return CountedStep(
        site_id="orthomcl",
        wdk_step_id=_STEP,
        record_type=record_type,
        search_name=search_name,
        record_noun=noun,
        step_url=step_url,
        refused=refused,
    )


def _recorded(name: str) -> RecordedWDKResponse:
    return RecordedWDKResponse.model_validate_json(
        qa_recording(SUITE_WDK_STORE / name).read_text()
    )


def _sequence_record_type() -> WDKRecordType:
    return WDKRecordType.model_validate(
        _recorded("orthomcl_sequence_record_type.json").body
    )


def _singleton_counts() -> WDKWordCounts:
    return WDKWordCounts.model_validate(
        _recorded("orthomcl_singleton_word_counts.json").body
    )


class _Site:
    def __init__(
        self,
        record_type: WDKRecordType,
        *,
        step_count: int,
        words: JsonValue = None,
        distribution: WDKColumnDistribution | None = None,
    ) -> None:
        self.record_type = record_type
        self.step_count = step_count
        self.words = words
        self.distribution = distribution
        self.reports: list[tuple[int, str]] = []
        self.distributions: list[tuple[int, str]] = []

    async def get_record_type_info(self, record_type: str) -> WDKRecordType:
        assert record_type == self.record_type.url_segment
        return self.record_type

    async def get_step_word_counts(self, step_id: int, reporter: str) -> WDKWordCounts:
        self.reports.append((step_id, reporter))
        return validate_response(
            WDKWordCounts, self.words, f"{reporter} report for step {step_id}"
        )

    async def get_step_count(self, step_id: int) -> int:
        assert step_id == _STEP
        return self.step_count

    async def get_column_distribution(
        self, step_id: int, column_name: str
    ) -> WDKColumnDistribution:
        self.distributions.append((step_id, column_name))
        assert self.distribution is not None
        return self.distribution


def _serve(monkeypatch: pytest.MonkeyPatch, site: _Site) -> _Site:
    tree = recorded_ortho_taxonomy()
    names = {node.code: node.label for node in tree.nodes() if not node.clade}

    async def genome_names(site_id: str) -> dict[str, str]:
        assert site_id == "orthomcl"
        return names

    monkeypatch.setattr(step_tally, "get_strategy_api", lambda _site_id: site)
    monkeypatch.setattr(step_tally, "genome_names", genome_names)
    return site


def _singletons(monkeypatch: pytest.MonkeyPatch, *, step_count: int) -> _Site:
    return _serve(
        monkeypatch,
        _Site(
            _sequence_record_type(),
            step_count=step_count,
            words=_singleton_counts().model_dump(mode="json"),
        ),
    )


async def test_the_proteins_of_a_step_are_counted_per_genome_by_their_word_cloud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _singletons(monkeypatch, step_count=523795)

    tally = await run_step_tally(
        _step("sequence", "FromGroups", "protein", _STEP_URL), "abbreviation"
    )

    assert site.reports == [(_STEP, "abbreviation-wordCloud")]
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
        _STEP_URL,
        "Taxon Code",
    )
    assert tally.id == tally_id("orthomcl", f"step {_STEP}", "abbreviation", None)
    assert tally.fact().count("bpli") == 18260


async def test_word_counts_that_are_not_the_steps_records_are_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _singletons(monkeypatch, step_count=523796)

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            _step("sequence", "FromGroups", "protein", None), "abbreviation"
        )

    message = str(refused.value)
    assert "523,796 protein records" in message
    assert "sum to 523,795" in message
    assert message.startswith("abbreviation (Taxon Code) cannot count the 523,796")


async def test_a_column_with_no_count_is_refused_with_the_columns_that_have_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _singletons(monkeypatch, step_count=523795)

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(_step("sequence", "FromGroups", "protein", None), "length")

    message = str(refused.value)
    assert message == (
        "protein records cannot be counted by length. The columns counted by their "
        "word cloud when every value is a genome code: abbreviation (Taxon Code)."
    )
    assert [
        name
        for name in (
            "product",
            "pfam_domains",
            "taxon_name",
            "ec_numbers",
            "group_link",
        )
        if name in message
    ] == []
    assert site.reports == []


async def test_a_column_refused_in_this_pass_is_not_offered_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _singletons(monkeypatch, step_count=523795)

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            _step(
                "sequence",
                "FromGroups",
                "protein",
                None,
                refused=frozenset({"abbreviation"}),
            ),
            "length",
        )

    assert str(refused.value) == (
        "protein records cannot be counted by length. No other column of these "
        "records can be counted."
    )


async def test_a_word_cloud_column_that_holds_no_genome_codes_is_refused_unread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _singletons(monkeypatch, step_count=523795)

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            _step("sequence", "FromGroups", "protein", None), "taxon_name"
        )

    assert str(refused.value) == (
        "taxon_name (Taxon Name) cannot be counted on step 227284080: the site "
        "counts it only by its word cloud, which splits and folds values into "
        "words, so only a column of genome codes is counted that way. The columns "
        "counted by their word cloud when every value is a genome code: "
        "abbreviation (Taxon Code)."
    )
    assert site.reports == []


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
                    "formats": [{"name": "length-histogram", "type": "histogram"}],
                }
            ],
        }
    )
    _serve(monkeypatch, _Site(record_type, step_count=1))

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(_step("sequence", "FromGroups", "protein", None), "length")

    assert str(refused.value) == (
        "protein records cannot be counted by length. No other column of these "
        "records can be counted."
    )


async def test_a_word_cloud_at_the_sites_cap_is_refused_by_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(
        monkeypatch,
        _Site(
            _sequence_record_type(),
            step_count=523795,
            words={"tags": [{"word": "Too many words", "count": 1}]},
        ),
    )

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            _step("sequence", "FromGroups", "protein", None), "abbreviation"
        )

    message = str(refused.value)
    assert message.startswith(
        "abbreviation (Taxon Code) cannot be counted on step 227284080: the site's "
        "word cloud answered no counts ("
    )
    assert "cap of 10,000 distinct words" in message
    assert message.endswith("No other column of these records can be counted.")


async def test_words_that_are_not_genome_codes_are_refused_though_they_sum(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(
        monkeypatch,
        _Site(
            _sequence_record_type(),
            step_count=2,
            words={"tags": [{"word": "kinase", "count": 2}]},
        ),
    )

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            _step("sequence", "FromGroups", "protein", None), "abbreviation"
        )

    assert str(refused.value) == (
        "abbreviation (Taxon Code) cannot be counted on step 227284080: the site "
        "counts it only by its word cloud, which splits and folds values into words, "
        "so its counts are taken only when every word is a genome code, and kinase "
        "is not. No other column of these records can be counted."
    )
    assert site.reports == [(_STEP, "abbreviation-wordCloud")]


async def test_a_column_with_a_by_value_report_is_counted_by_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record_type = WDKRecordType.model_validate(
        {
            "urlSegment": "transcript",
            "attributes": [
                {
                    "name": "organism",
                    "displayName": "Organism",
                    "tools": {"reports": ["byValue"], "filters": ["byValue"]},
                    "formats": [
                        {"name": "organism-wordCloud", "type": "wordCloud"},
                    ],
                }
            ],
        }
    )
    distribution = WDKColumnDistribution.model_validate(
        {
            "statistics": {
                "subsetSize": 412,
                "numDistinctValues": 2,
                "numMissingCases": 3,
            },
            "histogram": [
                {"value": 103, "binLabel": "<i>Plasmodium vivax</i> P01"},
                {"value": 306, "binLabel": "<i>Plasmodium falciparum</i> 3D7"},
            ],
        }
    )
    site = _serve(
        monkeypatch,
        _Site(record_type, step_count=412, distribution=distribution),
    )

    tally = await run_step_tally(
        _step("transcript", "GenesByTaxon", "gene", None), "organism"
    )

    assert site.distributions == [(_STEP, "organism")]
    assert site.reports == []
    assert [(row.value, row.count, row.label) for row in tally.rows] == [
        ("Plasmodium falciparum 3D7", 306, ""),
        ("Plasmodium vivax P01", 103, ""),
    ]
    assert (tally.total, tally.distinct, tally.missing) == (412, 2, 3)


_ORGANISM = WDKRecordType.model_validate(
    {
        "urlSegment": "transcript",
        "attributes": [
            {
                "name": "organism",
                "displayName": "Organism",
                "tools": {"reports": ["byValue"], "filters": ["byValue"]},
            },
            {
                "name": "gene_type",
                "displayName": "Gene Type",
                "tools": {"reports": ["byValue"], "filters": ["byValue"]},
            },
        ],
    }
)


async def test_the_clients_reply_to_a_site_error_is_refused_and_not_a_count_of_0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(
        monkeypatch,
        _Site(_ORGANISM, step_count=412, distribution=WDKColumnDistribution()),
    )

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            _step("transcript", "GenesByTaxon", "gene", None), "organism"
        )

    assert str(refused.value) == (
        "The site answered no counts for organism (Organism) on step 227284080, "
        "which holds 412 gene records."
    )
    assert site.reports == []


async def test_a_step_of_no_records_counts_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(
        monkeypatch,
        _Site(_ORGANISM, step_count=0, distribution=WDKColumnDistribution()),
    )

    tally = await run_step_tally(
        _step("transcript", "GenesByTaxon", "gene", None), "organism"
    )

    assert (tally.total, tally.distinct, tally.rows) == (0, 0, [])


async def test_a_column_no_record_holds_a_value_in_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = WDKColumnDistribution.model_validate(
        {"statistics": {"subsetSize": 412, "numMissingCases": 412}, "histogram": []}
    )
    _serve(monkeypatch, _Site(_ORGANISM, step_count=412, distribution=empty))

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_step_tally(
            _step("transcript", "GenesByTaxon", "gene", None), "organism"
        )

    assert str(refused.value) == (
        "None of the 412 gene records of step 227284080 has a value for organism "
        "(Organism), so it counts nothing. The columns the site counts by value: "
        "gene_type (Gene Type)."
    )


async def test_rows_are_named_only_when_every_value_is_a_genome_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mixed = WDKColumnDistribution.model_validate(
        {
            "statistics": {"subsetSize": 9, "numDistinctValues": 2},
            "histogram": [
                {"value": 5, "binLabel": "pfal"},
                {"value": 4, "binLabel": "Plasmodium vivax P01"},
            ],
        }
    )
    _serve(monkeypatch, _Site(_ORGANISM, step_count=9, distribution=mixed))

    tally = await run_step_tally(
        _step("transcript", "GenesByTaxon", "gene", None), "organism"
    )

    assert [(row.value, row.label) for row in tally.rows] == [
        ("pfal", ""),
        ("Plasmodium vivax P01", ""),
    ]
