from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.parameters import ParamValue
from veupathdb.errors import WDKError
from veupathdb.testing.wdk_fixtures import RecordedWDKResponse
from veupathdb.wdk import WDKDatasetConfigIdList, WDKSearch

from pathfinder.tests._support.qa_recording import SUITE_WDK_STORE, qa_recording
from pathfinder.tests._support.recorded_searches import suite_search

BY_ID_LIST = suite_search("search_sequences_by_id_list_orthomcl")
BY_ACCESSION = suite_search("search_sequences_by_accession_orthomcl")
GROUPS_FROM_SEQUENCES = suite_search("search_groups_from_sequences_orthomcl")
TYPED_GENE_ID = "PF3D7_1133400"
PROTEINS_OF_THE_TYPED_ID = 1


class _Meta(BaseModel):
    model_config = ConfigDict(extra="ignore")
    total_count: int = Field(alias="totalCount")


class _TotalCount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    meta: _Meta


def _recorded(name: str) -> RecordedWDKResponse:
    return RecordedWDKResponse.model_validate_json(
        qa_recording(SUITE_WDK_STORE / name).read_text()
    )


def recorded_refusal(search_name: str) -> WDKError:
    recorded = _recorded("refusal_by_accession_under_groups_orthomcl.json")
    text = (recorded.text or "").replace('"ByAccession"', f'"{search_name}"')
    return WDKError(text, status=recorded.provenance.status)


def recorded_accession_count() -> int:
    body = _recorded("report_sequences_by_accession_gene_id_orthomcl.json").json_body()
    return _TotalCount.model_validate(body).meta.total_count


@dataclass
class OrthoSite:
    held: dict[str, dict[str, WDKSearch]] = field(
        default_factory=lambda: {
            "sequence": {
                BY_ID_LIST.url_segment: BY_ID_LIST,
                BY_ACCESSION.url_segment: BY_ACCESSION,
            },
            "group": {GROUPS_FROM_SEQUENCES.url_segment: GROUPS_FROM_SEQUENCES},
        }
    )
    reads: list[tuple[str, str]] = field(default_factory=list)
    contexts: list[dict[str, str]] = field(default_factory=list)
    datasets: list[list[str]] = field(default_factory=list)
    counted: list[tuple[str, dict[str, ParamValue]]] = field(default_factory=list)

    def read(self, record_type: str, name: str) -> WDKSearch:
        self.reads.append((record_type, name))
        searches = self.held.get(record_type, {})
        if name not in searches:
            raise recorded_refusal(name)
        return searches[name]

    def count(self, name: str, params: dict[str, ParamValue]) -> int:
        self.counted.append((name, dict(params)))
        if name == BY_ACCESSION.url_segment:
            return recorded_accession_count()
        return PROTEINS_OF_THE_TYPED_ID

    async def create_dataset(self, config: WDKDatasetConfigIdList) -> int:
        self.datasets.append(config.source_content.ids)
        return 9001 + len(self.datasets) - 1
