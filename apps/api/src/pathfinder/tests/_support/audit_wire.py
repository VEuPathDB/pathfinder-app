from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import respx
from pydantic import BaseModel, Field
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import get_site

from pathfinder.domain.audit.scope import GenePairTarget

SITE = "plasmodb"
DD2 = "Plasmodium falciparum Dd2"
DD2_YIP1 = "PfDd2_140076300"
P3D7_YIP1 = "PF3D7_1472100"
UNFLAGGED_STRAIN = GenePairTarget(check="pseudogene_call", genes=(DD2_YIP1, P3D7_YIP1))
_USER = 376
_RECORDS: dict[str, dict[str, object]] = {
    P3D7_YIP1: {
        "attributes": {
            "organism_full": "Plasmodium falciparum 3D7",
            "orthomcl_name": "OG8_0005198",
            "name": "YIP1",
            "product": "protein transport protein YIP1, putative",
            "sequence_id": "Pf3D7_14_v3",
            "start_min": "2941398",
            "end_max": "2945279",
            "strand_plus_minus": "-",
            "is_pseudo": "No",
            "gene_type": "protein coding gene",
        },
        "transcripts": [{"transcript_id": "PF3D7_1472100.1", "protein_length": "314"}],
    },
    DD2_YIP1: {
        "attributes": {
            "organism_full": DD2,
            "orthomcl_name": "OG8_0005198",
            "name": "YIP1",
            "product": "protein transport protein YIP1, putative",
            "sequence_id": "PfDd2_14",
            "start_min": "2919589",
            "end_max": "2921032",
            "strand_plus_minus": "-",
            "is_pseudo": "No",
            "gene_type": "protein coding gene",
        },
        "transcripts": [
            {"transcript_id": "PfDd2_140076300-t41_1", "protein_length": "289"}
        ],
    },
}


class _PrimaryKey(BaseModel):
    name: str
    value: str


class _RecordRequest(BaseModel):
    primary_key: list[_PrimaryKey] = Field(alias="primaryKey")


def _record(gene: str, *, readable: bool) -> dict[str, object]:
    held = _RECORDS[gene]
    return {
        "displayName": gene,
        "id": [
            {"name": "source_id", "value": gene},
            {"name": "project_id", "value": "PlasmoDB"},
        ],
        "recordClassName": "GeneRecordClasses.GeneRecordClass",
        "attributes": held["attributes"],
        "tables": {"GeneTranscripts": held["transcripts"]} if readable else {},
        "tableErrors": [],
    }


@contextmanager
def yip1_records(*, readable: bool = True) -> Iterator[respx.Route]:
    site = get_site(SITE)
    service = site.service_url
    token = veupathdb_auth_token_ctx.set("a-registered-token")

    def answer(request: httpx.Request) -> httpx.Response:
        asked = _RecordRequest.model_validate_json(request.content)
        gene = next(
            part.value for part in asked.primary_key if part.name == "source_id"
        )
        return httpx.Response(200, json=_record(gene, readable=readable))

    try:
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.get(f"{site.web_base_url}/app").mock(
                return_value=httpx.Response(200)
            )
            router.get(f"{service}/users/current").mock(
                return_value=httpx.Response(200, json={"id": _USER, "isGuest": False})
            )
            yield router.post(f"{service}/record-types/gene/records").mock(
                side_effect=answer
            )
    finally:
        veupathdb_auth_token_ctx.reset(token)
