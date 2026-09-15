"""The ids a step yields are gene ids, each once, in the order the site returns them."""

from __future__ import annotations

from veupathdb.wdk import StrategyAPI, WDKAnswer, WDKRecordInstance

from pathfinder.services.gene_sets.step_genes import extract_gene_id, fetch_all_gene_ids


def _transcript(transcript_id: str, gene_id: str) -> WDKRecordInstance:
    return WDKRecordInstance.model_validate(
        {
            "displayName": transcript_id,
            "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
            "id": [
                {"name": "source_id", "value": transcript_id},
                {"name": "gene_source_id", "value": gene_id},
            ],
        }
    )


def _gene(gene_id: str) -> WDKRecordInstance:
    return WDKRecordInstance.model_validate(
        {
            "displayName": gene_id,
            "recordClassName": "GeneRecordClasses.GeneRecordClass",
            "id": [{"name": "source_id", "value": gene_id}],
        }
    )


class _StepAnswers(StrategyAPI):
    """A strategy API that answers one step with the records it was given."""

    def __init__(self, records: list[WDKRecordInstance]) -> None:
        self._records = records
        self.calls = 0

    async def get_step_answer(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        user_id: str | None = None,
    ) -> WDKAnswer:
        self.calls += 1
        window = pagination or {"offset": 0, "numRecords": len(self._records)}
        start = window["offset"]
        page = self._records[start : start + window["numRecords"]]
        return WDKAnswer.model_validate(
            {
                "meta": {"totalCount": len(self._records), "recordClassName": "x"},
                "records": [r.model_dump(by_alias=True) for r in page],
            }
        )


def test_a_transcript_record_yields_its_gene_id() -> None:
    record = _transcript("PF3D7_0107600.1", "PF3D7_0107600")

    assert extract_gene_id(record) == "PF3D7_0107600"


def test_a_gene_record_yields_its_own_id() -> None:
    assert extract_gene_id(_gene("PF3D7_0211700")) == "PF3D7_0211700"


async def test_two_transcripts_of_one_gene_count_once() -> None:
    api = _StepAnswers(
        [
            _transcript("PF3D7_0107600.1", "PF3D7_0107600"),
            _transcript("PF3D7_0211700.1", "PF3D7_0211700"),
            _transcript("PF3D7_0107600.2", "PF3D7_0107600"),
        ]
    )

    ids = await fetch_all_gene_ids(api, 227292220, batch_size=2)

    assert ids == ["PF3D7_0107600", "PF3D7_0211700"]
    assert api.calls == 2
