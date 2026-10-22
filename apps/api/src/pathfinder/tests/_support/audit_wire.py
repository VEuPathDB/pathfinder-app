from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import httpx
import respx
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.wdk import get_site

from pathfinder.domain.audit.scope import GenePairTarget

SITE = "plasmodb"
DD2 = "Plasmodium falciparum Dd2"
DD2_YIP1 = "PfDd2_140076300"
P3D7_YIP1 = "PF3D7_1472100"
UNFLAGGED_STRAIN = GenePairTarget(check="pseudogene_call", genes=(DD2_YIP1, P3D7_YIP1))
_USER = 376
_DATASET = 9
_ATTRIBUTES = [
    "organism_full",
    "gene_orthomcl_name",
    "protein_length",
    "gene_name",
    "gene_product",
    "sequence_id",
    "gene_start_min",
    "gene_end_max",
    "strand_plus_minus",
    "is_pseudo",
    "gene_type",
    "input_id",
]
_RECORDS = [
    {
        "displayName": P3D7_YIP1,
        "id": [
            {"name": "gene_source_id", "value": P3D7_YIP1},
            {"name": "source_id", "value": "PF3D7_1472100.1"},
            {"name": "project_id", "value": "PlasmoDB"},
        ],
        "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
        "attributes": {
            "gene_orthomcl_name": "OG8_0005198",
            "protein_length": "314",
            "gene_name": "YIP1",
            "organism_full": "Plasmodium falciparum 3D7",
            "gene_start_min": "2941398",
            "gene_type": "protein coding gene",
            "sequence_id": "Pf3D7_14_v3",
            "is_pseudo": "No",
            "gene_product": "protein transport protein YIP1, putative",
            "gene_end_max": "2945279",
            "strand_plus_minus": "-",
            "input_id": P3D7_YIP1,
        },
        "tables": {},
        "tableErrors": [],
    },
    {
        "displayName": DD2_YIP1,
        "id": [
            {"name": "gene_source_id", "value": DD2_YIP1},
            {"name": "source_id", "value": "PfDd2_140076300-t41_1"},
            {"name": "project_id", "value": "PlasmoDB"},
        ],
        "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
        "attributes": {
            "gene_orthomcl_name": "OG8_0005198",
            "protein_length": "289",
            "gene_name": "YIP1",
            "organism_full": DD2,
            "gene_start_min": "2919589",
            "gene_type": "protein coding gene",
            "sequence_id": "PfDd2_14",
            "is_pseudo": "No",
            "gene_product": "protein transport protein YIP1, putative",
            "gene_end_max": "2921032",
            "strand_plus_minus": "-",
            "input_id": DD2_YIP1,
        },
        "tables": {},
        "tableErrors": [],
    },
]


def _answer(total: int) -> dict[str, object]:
    count = len(_RECORDS)
    return {
        "meta": {
            "totalCount": total,
            "responseCount": count,
            "displayTotalCount": total,
            "viewTotalCount": total,
            "displayViewTotalCount": total,
            "recordClassName": "transcript",
            "attributes": _ATTRIBUTES,
            "tables": [],
        },
        "records": _RECORDS,
    }


@contextmanager
def yip1_rows(*, total: int = len(_RECORDS)) -> Iterator[respx.Route]:
    site = get_site(SITE)
    service = site.service_url
    token = veupathdb_auth_token_ctx.set("a-registered-token")
    try:
        with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
            router.get(f"{site.web_base_url}/app").mock(
                return_value=httpx.Response(200)
            )
            router.get(f"{service}/users/current").mock(
                return_value=httpx.Response(200, json={"id": _USER, "isGuest": False})
            )
            router.post(f"{service}/users/{_USER}/datasets").mock(
                return_value=httpx.Response(200, json={"id": _DATASET})
            )
            yield router.post(
                f"{service}/record-types/transcript/searches/GeneByLocusTag/reports/standard"
            ).mock(return_value=httpx.Response(200, json=_answer(total)))
    finally:
        veupathdb_auth_token_ctx.reset(token)
