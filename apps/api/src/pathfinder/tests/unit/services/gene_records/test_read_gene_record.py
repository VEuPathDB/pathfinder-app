"""One gene record, read from the attributes a site declares."""

from __future__ import annotations

from collections.abc import Mapping

import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import (
    AiExpressionStatus,
    StrategyAPI,
    WDKRecordInstance,
    WDKRecordType,
)
from veupathdb_mcp.wdk import GeneExpressionSummary

from pathfinder.services.gene_records import read
from pathfinder.services.gene_records.read import (
    UnknownGeneRecordError,
    read_the_gene_record,
)

TOXO_ATTRIBUTES = (
    "organism",
    "product",
    "name",
    "chromosome",
    "exon_count",
    "transcript_count",
    "sequence_id",
)

_SRS29B = {
    "organism": "Toxoplasma gondii ME49",
    "product": "SAG-related sequence SRS29B",
    "name": "SRS29B",
    "chromosome": "VIII",
    "exon_count": "1",
    "transcript_count": "1",
}

_ORTHOLOGS = [
    {
        "organism": f"Ortholog organism {index}",
        "ortho_gene_source_id": f"OGS_{index:03d}",
        "gene": {"displayText": f"OGS_{index:03d}", "url": "https://toxodb.org/x"},
    }
    for index in range(14)
]


def _record(
    attributes: Mapping[str, object], tables: Mapping[str, object]
) -> WDKRecordInstance:
    return WDKRecordInstance.model_validate(
        {
            "displayName": "TGME49_233460",
            "recordClassName": "GeneRecordClasses.GeneRecordClass",
            "id": [
                {"name": "source_id", "value": "TGME49_233460"},
                {"name": "project_id", "value": "ToxoDB"},
            ],
            "attributes": dict(attributes),
            "tables": dict(tables),
        }
    )


def _record_type(names: tuple[str, ...]) -> WDKRecordType:
    return WDKRecordType.model_validate(
        {
            "urlSegment": "gene",
            "primaryKeyColumnRefs": ["source_id", "project_id"],
            "attributes": [{"name": name} for name in names],
        }
    )


class _GeneRecord(StrategyAPI):
    """A strategy API that answers one gene record on one site."""

    def __init__(
        self,
        record: WDKRecordInstance,
        *,
        declares: tuple[str, ...] = TOXO_ATTRIBUTES,
    ) -> None:
        self._record = record
        self._declares = declares
        self.asked_attributes: list[str] = []
        self.asked_tables: list[str] = []
        self.record_type_calls = 0

    async def get_record_type_info(self, record_type: str) -> WDKRecordType:
        self.record_type_calls += 1
        assert record_type == "gene"
        return _record_type(self._declares)

    async def get_single_record(
        self,
        record_type: str,
        primary_key: list[dict[str, str]],
        *,
        attributes: list[str] | None = None,
        tables: list[str] | None = None,
    ) -> WDKRecordInstance:
        del record_type
        self.primary_key = primary_key
        self.asked_attributes = list(attributes or [])
        self.asked_tables = list(tables or [])
        return self._record


class _NoSuchGene(StrategyAPI):
    """A strategy API whose site holds no record for the id it is asked."""

    def __init__(self) -> None:
        self.declares = TOXO_ATTRIBUTES

    async def get_record_type_info(self, record_type: str) -> WDKRecordType:
        del record_type
        return _record_type(self.declares)

    async def get_single_record(
        self,
        record_type: str,
        primary_key: list[dict[str, str]],
        *,
        attributes: list[str] | None = None,
        tables: list[str] | None = None,
    ) -> WDKRecordInstance:
        del record_type, primary_key, attributes, tables
        refusal = "record not found"
        raise WDKError(refusal, status=404)


@pytest.fixture(autouse=True)
def _forget_record_types(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test reads the site's record type for itself."""
    monkeypatch.setattr(read, "_gene_record_types", {})


@pytest.fixture
def _no_expression(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _none(site_id: str, gene_id: str) -> GeneExpressionSummary:
        return GeneExpressionSummary(
            site_id=site_id,
            gene_id=gene_id,
            result_status=AiExpressionStatus.MISSING,
            unavailable_reason="no summary",
        )

    monkeypatch.setattr(read, "get_gene_expression_summary", _none)


@pytest.mark.usefixtures("_no_expression")
async def test_the_summary_carries_the_facts_the_record_states() -> None:
    api = _GeneRecord(_record(dict(_SRS29B), {"Orthologs": _ORTHOLOGS}))

    found = await read_the_gene_record(api, "toxodb", "TGME49_233460")

    assert found.product == "SAG-related sequence SRS29B"
    assert found.exon_count == 1
    assert found.transcript_count == 1
    assert found.chromosome == "VIII"
    assert found.gene_name == "SRS29B"
    assert found.organism == "Toxoplasma gondii ME49"
    assert found.record_url == "https://toxodb.org/toxo/app/record/gene/TGME49_233460"


@pytest.mark.usefixtures("_no_expression")
async def test_the_summary_lists_the_orthologs_and_their_total() -> None:
    api = _GeneRecord(_record(dict(_SRS29B), {"Orthologs": _ORTHOLOGS}))

    found = await read_the_gene_record(api, "toxodb", "TGME49_233460")

    assert found.ortholog_count == 14
    assert len(found.orthologs) == 14
    assert found.orthologs[0].gene_id == "OGS_000"
    assert found.orthologs[0].organism == "Ortholog organism 0"


@pytest.mark.usefixtures("_no_expression")
async def test_only_twenty_ortholog_rows_ride_the_summary() -> None:
    rows = [
        {"organism": f"Organism {i}", "ortho_gene_source_id": f"G{i}"}
        for i in range(31)
    ]
    api = _GeneRecord(_record(dict(_SRS29B), {"Orthologs": rows}))

    found = await read_the_gene_record(api, "toxodb", "TGME49_233460")

    assert found.ortholog_count == 31
    assert len(found.orthologs) == 20


@pytest.mark.usefixtures("_no_expression")
async def test_a_site_without_chromosome_is_never_asked_for_it() -> None:
    """An attribute the record type does not declare makes WDK answer a 500."""
    declares = tuple(n for n in TOXO_ATTRIBUTES if n != "chromosome")
    attributes = {k: v for k, v in _SRS29B.items() if k != "chromosome"}
    api = _GeneRecord(_record(attributes, {}), declares=declares)

    found = await read_the_gene_record(api, "cryptodb", "cgd6_1080")

    assert "chromosome" not in api.asked_attributes
    assert api.asked_attributes == [
        "organism",
        "product",
        "name",
        "exon_count",
        "transcript_count",
    ]
    assert found.chromosome is None


@pytest.mark.usefixtures("_no_expression")
async def test_the_record_type_is_read_once_per_site() -> None:
    api = _GeneRecord(_record(dict(_SRS29B), {}))

    await read_the_gene_record(api, "toxodb", "TGME49_233460")
    await read_the_gene_record(api, "toxodb", "TGME49_233460")

    assert api.record_type_calls == 1


@pytest.mark.usefixtures("_no_expression")
async def test_the_primary_key_names_the_gene_and_the_project() -> None:
    api = _GeneRecord(_record(dict(_SRS29B), {}))

    await read_the_gene_record(api, "toxodb", "TGME49_233460")

    assert api.primary_key == [
        {"name": "source_id", "value": "TGME49_233460"},
        {"name": "project_id", "value": "ToxoDB"},
    ]
    assert api.asked_tables == ["Orthologs"]


async def test_an_unknown_gene_id_is_a_typed_not_found() -> None:
    with pytest.raises(UnknownGeneRecordError) as refused:
        await read_the_gene_record(_NoSuchGene(), "toxodb", "TGME49_000000")

    assert refused.value.status == 404
    assert "TGME49_000000" in str(refused.value)


async def test_the_site_summary_of_the_expression_rides_the_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _summary(site_id: str, gene_id: str) -> GeneExpressionSummary:
        return GeneExpressionSummary.model_validate(
            {
                "siteId": site_id,
                "geneId": gene_id,
                "resultStatus": "present",
                "numExperiments": 12,
                "basedOnIncompleteData": True,
                "summary": {
                    "headline": "Highest in the tachyzoite stage",
                    "one_paragraph_summary": "Expression peaks in tachyzoites.",
                },
            }
        )

    monkeypatch.setattr(read, "get_gene_expression_summary", _summary)
    api = _GeneRecord(_record(dict(_SRS29B), {}))

    found = await read_the_gene_record(api, "toxodb", "TGME49_233460")

    assert found.expression is not None
    assert found.expression.headline == "Highest in the tachyzoite stage"
    assert found.expression.experiments == 12
    assert found.expression.covers_part_of_the_experiments is True


async def test_a_site_that_serves_no_expression_report_still_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _refuses(site_id: str, gene_id: str) -> GeneExpressionSummary:
        del site_id, gene_id
        refusal = "no expression reporter here"
        raise WDKError(refusal, status=500)

    monkeypatch.setattr(read, "get_gene_expression_summary", _refuses)
    api = _GeneRecord(_record(dict(_SRS29B), {}))

    found = await read_the_gene_record(api, "toxodb", "TGME49_233460")

    assert found.expression is None
    assert found.product == "SAG-related sequence SRS29B"


@pytest.mark.usefixtures("_no_expression")
async def test_the_summary_line_names_the_record_in_one_sentence() -> None:
    api = _GeneRecord(_record(dict(_SRS29B), {"Orthologs": _ORTHOLOGS}))

    found = await read_the_gene_record(api, "toxodb", "TGME49_233460")

    assert found.summary_line() == (
        "TGME49_233460: SAG-related sequence SRS29B, 1 exon, "
        "chromosome VIII, 14 orthologs"
    )
