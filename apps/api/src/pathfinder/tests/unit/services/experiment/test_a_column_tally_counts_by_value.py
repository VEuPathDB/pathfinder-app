"""A column tally counts one search's records by each value of one column, with
the site's own column reporter, after keeping only the rows another column
holds a value for."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.wdk import WDKSearchConfig
from veupathdb.wdk.wdk_models import WDKColumnDistribution, WDKRecordType

from pathfinder.domain.tally_facts import tally_id
from pathfinder.services.experiment import column_tally
from pathfinder.services.experiment.column_tally import (
    ColumnTallyRefusedError,
    TallyOnly,
    run_column_tally,
)
from pathfinder.services.experiment.variant_comparison import VariantSpec

_SPEC = VariantSpec(
    label="datasets",
    search_name="AllDatasets",
    record_type="dataset",
    parameters={},
)

_RECORD_TYPE = WDKRecordType.model_validate(
    {
        "urlSegment": "dataset",
        "attributes": [
            {
                "name": "organism_prefix",
                "displayName": "Organism(s)",
                "columnDataType": "STRING",
                "tools": {"reports": ["byValue"], "filters": ["byValue"]},
            },
            {
                "name": "newcategory",
                "displayName": "Category",
                "columnDataType": "STRING",
                "tools": {"reports": ["byValue"], "filters": ["byValue"]},
            },
            {
                "name": "overview",
                "displayName": "Overview",
                "columnDataType": "STRING",
            },
        ],
    }
)

_REPLY = WDKColumnDistribution.model_validate(
    {
        "statistics": {"subsetSize": 379, "numDistinctValues": 3},
        "histogram": [
            {
                "value": 11,
                "binStart": "<i>Anopheles coluzzii</i> AcolN3",
                "binLabel": "<i>Anopheles coluzzii</i> AcolN3",
            },
            {
                "value": 67,
                "binStart": "<i>Aedes aegypti</i> LVP_AGWG",
                "binLabel": "<i>Aedes aegypti</i> LVP_AGWG",
            },
            {
                "value": 40,
                "binStart": "<i>Anopheles gambiae</i> PEST",
                "binLabel": "<i>Anopheles gambiae</i> PEST",
            },
        ],
    }
)

_CATEGORIES = WDKColumnDistribution.model_validate(
    {
        "statistics": {"subsetSize": 627, "numDistinctValues": 2},
        "histogram": [
            {"value": 105, "binStart": "Genomes", "binLabel": "Genomes"},
            {"value": 379, "binStart": "RNASeq", "binLabel": "RNASeq"},
        ],
    }
)


class _Site:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, WDKSearchConfig, str]] = []

    async def get_record_type_info(self, record_type: str) -> WDKRecordType:
        assert record_type == "dataset"
        return _RECORD_TYPE

    async def run_search_column_report(
        self,
        record_type: str,
        search_name: str,
        search_config: WDKSearchConfig,
        column: str,
        **_: Any,
    ) -> WDKColumnDistribution:
        self.sent.append((record_type, search_name, search_config, column))
        return _REPLY


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> _Site:
    fake = _Site()
    monkeypatch.setattr(column_tally, "get_strategy_api", lambda _site_id: fake)
    monkeypatch.setattr(column_tally, "get_wdk_client", lambda _site_id: fake)
    return fake


class _Answers(_Site):
    def __init__(self, by_column: dict[str, WDKColumnDistribution]) -> None:
        super().__init__()
        self.by_column = by_column

    async def run_search_column_report(
        self,
        record_type: str,
        search_name: str,
        search_config: WDKSearchConfig,
        column: str,
        **_: Any,
    ) -> WDKColumnDistribution:
        self.sent.append((record_type, search_name, search_config, column))
        return self.by_column[column]


def _answering(
    monkeypatch: pytest.MonkeyPatch, by_column: dict[str, WDKColumnDistribution]
) -> _Answers:
    fake = _Answers(by_column)
    monkeypatch.setattr(column_tally, "get_strategy_api", lambda _site_id: fake)
    monkeypatch.setattr(column_tally, "get_wdk_client", lambda _site_id: fake)
    return fake


async def test_the_column_is_counted_after_the_rows_are_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _answering(
        monkeypatch, {"organism_prefix": _REPLY, "newcategory": _CATEGORIES}
    )

    tally = await run_column_tally(
        "vectorbase",
        _SPEC,
        "organism_prefix",
        TallyOnly(column="newcategory", values=["RNASeq"]),
        record_noun="dataset",
    )

    (_, (record_type, search_name, config, column)) = site.sent
    assert (record_type, search_name, column) == (
        "dataset",
        "AllDatasets",
        "organism_prefix",
    )
    assert config.column_filters == {"newcategory": {"byValue": {"values": ["RNASeq"]}}}
    assert [(row.value, row.count) for row in tally.rows] == [
        ("Aedes aegypti LVP_AGWG", 67),
        ("Anopheles gambiae PEST", 40),
        ("Anopheles coluzzii AcolN3", 11),
    ]
    assert (tally.total, tally.distinct) == (379, 3)
    assert tally.title == "Datasets by Organism(s), where Category is RNASeq"
    assert tally.id == tally_id(
        "vectorbase", "AllDatasets", "organism_prefix", ("newcategory", ("RNASeq",))
    )
    assert {row.value: row.count for row in tally.fact().rows}[
        "Anopheles gambiae PEST"
    ] == 40


async def test_a_value_named_as_shown_is_sent_as_the_site_stores_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _answering(
        monkeypatch, {"organism_prefix": _REPLY, "newcategory": _CATEGORIES}
    )

    await run_column_tally(
        "vectorbase",
        _SPEC,
        "newcategory",
        TallyOnly(column="organism_prefix", values=["Anopheles gambiae PEST"]),
        record_noun="dataset",
    )

    assert site.sent[-1][2].column_filters == {
        "organism_prefix": {"byValue": {"values": ["<i>Anopheles gambiae</i> PEST"]}}
    }


async def test_a_column_the_site_does_not_count_is_refused_with_those_it_does(
    site: _Site,
) -> None:
    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_column_tally(
            "vectorbase", _SPEC, "overview", None, record_noun="dataset"
        )

    assert str(refused.value) == (
        "dataset records cannot be counted by overview. The columns they can be "
        "counted by: organism_prefix (Organism(s)), newcategory (Category)."
    )
    assert site.sent == []


async def test_a_column_the_site_does_not_filter_on_is_refused(site: _Site) -> None:
    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_column_tally(
            "vectorbase",
            _SPEC,
            "organism_prefix",
            TallyOnly(column="overview", values=["x"]),
            record_noun="dataset",
        )

    assert str(refused.value).startswith("dataset records cannot be kept by overview.")
    assert site.sent == []


async def test_a_column_no_record_has_a_value_in_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = WDKColumnDistribution.model_validate(
        {
            "statistics": {"subsetSize": 379, "numDistinctValues": 0},
            "histogram": [],
        }
    )
    _answering(monkeypatch, {"organism_prefix": empty, "newcategory": _CATEGORIES})

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_column_tally(
            "vectorbase",
            _SPEC,
            "organism_prefix",
            TallyOnly(column="newcategory", values=["RNASeq"]),
            record_noun="dataset",
        )

    assert str(refused.value) == (
        "None of the 379 dataset records has a value for organism_prefix "
        "(Organism(s)), so it counts nothing. Count them by another column."
    )


async def test_a_value_the_filter_column_does_not_hold_is_refused_with_those_it_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _answering(
        monkeypatch, {"organism_prefix": _REPLY, "newcategory": _CATEGORIES}
    )

    with pytest.raises(ColumnTallyRefusedError) as refused:
        await run_column_tally(
            "vectorbase",
            _SPEC,
            "organism_prefix",
            TallyOnly(column="newcategory", values=["RNA-Seq"]),
            record_noun="dataset",
        )

    assert str(refused.value) == (
        "No dataset record has newcategory (Category) RNA-Seq. The values "
        "newcategory holds: RNASeq, Genomes."
    )
    assert [(column, config.column_filters) for _, _, config, column in site.sent] == [
        ("newcategory", None)
    ]


async def test_a_blank_value_is_no_row(monkeypatch: pytest.MonkeyPatch) -> None:
    with_blank = WDKColumnDistribution.model_validate(
        {
            "statistics": {"subsetSize": 627, "numDistinctValues": 2},
            "histogram": [
                {"value": 379, "binLabel": "RNASeq"},
                {"value": 4, "binLabel": " "},
            ],
        }
    )
    _answering(monkeypatch, {"newcategory": with_blank})

    tally = await run_column_tally(
        "vectorbase", _SPEC, "newcategory", None, record_noun="dataset"
    )

    assert [(row.value, row.count) for row in tally.rows] == [("RNASeq", 379)]
