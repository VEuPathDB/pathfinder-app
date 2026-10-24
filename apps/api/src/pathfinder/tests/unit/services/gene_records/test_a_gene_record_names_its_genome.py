from __future__ import annotations

import pytest
from veupathdb.wdk import StrategyAPI, WDKRecordInstance, WDKRecordType

from pathfinder.services.gene_records import read
from pathfinder.services.gene_records.genome import read_the_gene_genome
from pathfinder.tests._support.audit_model_wire import SELK_WIRE

_FULL, _ABBREVIATED = SELK_WIRE.records[0], SELK_WIRE.records[6]


class _RecordedGene(StrategyAPI):
    def __init__(self, record: WDKRecordInstance) -> None:
        self._record = record
        self.asked: list[tuple[list[str], list[str]]] = []

    async def get_record_type_info(self, record_type: str) -> WDKRecordType:
        assert record_type == "gene"
        return WDKRecordType.model_validate(
            {
                "urlSegment": "gene",
                "primaryKeyColumnRefs": ["source_id", "project_id"],
                "attributes": [],
            }
        )

    async def get_single_record(
        self,
        record_type: str,
        primary_key: list[dict[str, str]],
        *,
        attributes: list[str] | None = None,
        tables: list[str] | None = None,
    ) -> WDKRecordInstance:
        del record_type, primary_key
        self.asked.append((list(attributes or []), list(tables or [])))
        return self._record


@pytest.fixture(autouse=True)
def _forget_record_types(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(read, "_gene_record_types", {})


async def test_a_gene_record_names_its_genome_in_full_not_abbreviated() -> None:
    api = _RecordedGene(WDKRecordInstance.model_validate(_FULL.body))
    abbreviated = WDKRecordInstance.model_validate(_ABBREVIATED.body)

    genome = await read_the_gene_genome(api, "toxodb", "TGGT1_316600")

    assert (genome, abbreviated.attribute_text("organismAbbrev")) == (
        "Toxoplasma gondii GT1",
        "tgonGT1",
    )
    assert api.asked == [(["organism_full"], [])]
